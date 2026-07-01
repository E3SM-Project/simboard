"""Scan archives and upload cases to SimBoard as single-case archives.

This runner mirrors the NERSC path-ingestor state/dedupe behavior, but instead
of sending a filesystem path it packages each submission-qualified case
into a temporary ``.tar.gz`` archive and uploads it to the dedicated
``/api/v1/ingestions/from-hpc-upload`` endpoint.

More information can be found in ``nersc_archive_ingestor.py``.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from app.features.ingestion.parsers.parser import _locate_metadata_files
from app.scripts.ingestion.nersc_archive_ingestor import (
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _build_config_from_env,
    _build_state_endpoint_url,
    _fetch_ingestion_state,
    _handle_dry_run,
    _handle_ingest_run,
    _is_transient_status,
    _log_event,
    _log_startup_configuration,
    _normalized_api_base_url,
    _scan_archive,
)


def main() -> int:
    """Build runtime configuration and execute upload ingestor."""
    try:
        config = _build_config_from_env()
    except ValueError as exc:
        _log_event("configuration_error", {"error": str(exc)})
        return 1

    start_time = time.monotonic()
    _log_event(
        "run_started",
        {
            "mode": "dry-run" if config.dry_run else "ingest",
            "archive_root": str(config.archive_root),
        },
    )
    exit_code = _run_ingestor(config)
    _log_event(
        "run_finished",
        {
            "mode": "dry-run" if config.dry_run else "ingest",
            "exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - start_time, 3),
        },
    )
    return exit_code


def _run_ingestor(
    config: IngestorConfig,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    sleep_fn: Callable[[float], None] = time.sleep,
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> int:
    """Execute one complete archive scan-and-upload cycle."""
    if post_request_fn is None:
        post_request_fn = _post_hpc_upload_ingestion_request

    endpoint_url = _build_endpoint_url(config)
    state_endpoint_url = _build_state_endpoint_url(config)
    _log_startup_configuration(
        config,
        endpoint_url=endpoint_url,
        state_endpoint_url=state_endpoint_url,
    )

    if not config.archive_root.is_dir():
        _log_event(
            "archive_root_missing",
            {"archive_root": str(config.archive_root)},
        )
        return 1

    if not config.api_token:
        _log_event("configuration_error", {"error": "SIMBOARD_API_TOKEN is required"})
        return 1

    try:
        state = _fetch_ingestion_state(
            state_endpoint_url,
            config.api_token,
            config.machine_name,
            timeout_seconds=config.request_timeout_seconds,
        )
    except IngestionRequestError as exc:
        _log_event(
            "state_fetch_failed",
            {
                "machine_name": config.machine_name,
                "status_code": exc.status_code,
                "error": str(exc),
            },
        )
        return 1

    (
        scan_results,
        candidates,
        submission_qualified_case_count,
        discovery_stats,
    ) = _scan_archive(config, state, metadata_locator=metadata_locator)

    _log_event(
        "scan_completed",
        {
            "archive_root": str(config.archive_root),
            "discovered_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
        },
    )

    if config.dry_run:
        return _handle_dry_run(
            candidates,
            scan_results,
            submission_qualified_case_count,
            discovery_stats,
            archive_root=config.archive_root,
        )

    return _handle_ingest_run(
        candidates,
        scan_results,
        config,
        endpoint_url,
        state,
        submission_qualified_case_count,
        discovery_stats,
        sleep_fn=sleep_fn,
        post_request_fn=post_request_fn,
    )


def _build_endpoint_url(config: IngestorConfig) -> str:
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/from-hpc-upload"


def _create_case_archive(case_path: str, staging_dir: Path) -> Path:
    """Package one case directory into a tar.gz archive."""
    case_dir = Path(case_path)
    if not case_dir.is_dir():
        raise IngestionRequestError(
            f"Case path is not a directory: {case_path}",
            status_code=None,
            transient=False,
        )

    case_hash = hashlib.sha256(case_path.encode("utf-8")).hexdigest()[:12]
    archive_path = staging_dir / f"{case_dir.name or 'case'}-{case_hash}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar_file:
        tar_file.add(case_dir, arcname=case_dir.name)

    return archive_path


def _encode_multipart_form_data(
    *,
    archive_path: Path,
    machine_name: str,
    case_path: str,
    processed_execution_ids: list[str],
) -> tuple[bytes, str]:
    """Build multipart/form-data body for one archive upload request."""
    boundary = f"----SimBoardBoundary{uuid.uuid4().hex}"
    body = bytearray()

    def _append_text_part(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    _append_text_part("machine_name", machine_name)
    _append_text_part("case_path", case_path)
    for execution_id in processed_execution_ids:
        _append_text_part("processed_execution_ids", execution_id)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{archive_path.name}"\r\n'
        ).encode("utf-8")
    )
    body.extend(b"Content-Type: application/gzip\r\n\r\n")
    body.extend(archive_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    return bytes(body), boundary


def _post_hpc_upload_ingestion_request(
    endpoint_url: str,
    api_token: str,
    archive_path: str,
    machine_name: str,
    *,
    processed_execution_ids: list[str],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """Upload one case directory as a multipart archive request."""
    with tempfile.TemporaryDirectory() as tmpdir:
        staged_archive = _create_case_archive(archive_path, Path(tmpdir))
        body, boundary = _encode_multipart_form_data(
            archive_path=staged_archive,
            machine_name=machine_name,
            case_path=archive_path,
            processed_execution_ids=processed_execution_ids,
        )

        request = urllib.request.Request(
            endpoint_url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                parsed_body = json.loads(raw_body) if raw_body else {}
                return {
                    "status_code": response.status,
                    "body": parsed_body,
                }
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            raise IngestionRequestError(
                f"HTTP {exc.code}: {response_text}",
                status_code=exc.code,
                transient=_is_transient_status(exc.code),
            ) from exc
        except urllib.error.URLError as exc:
            raise IngestionRequestError(
                f"URL error: {exc.reason}",
                status_code=None,
                transient=True,
            ) from exc
        except TimeoutError as exc:
            raise IngestionRequestError(
                "Request timed out",
                status_code=None,
                transient=True,
            ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
