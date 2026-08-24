"""Scan HPC archives and upload cases to SimBoard as single-case archives.

This script is intended for scheduled execution against a performance archive
that is not mounted in the SimBoard backend environment. Runtime configuration
is read from environment variables (for example ``SIMBOARD_API_BASE_URL``,
``SIMBOARD_API_TOKEN``, ``PERF_ARCHIVE_ROOT``, ``OLD_PERF_ARCHIVE_ROOT``, and ``DRY_RUN``).

Each ingest run executes these phases:

    1. In archive mode, fetch completed snapshot checkpoints.
    2. Fetch persisted per-case state from SimBoard API.
    3. Discover and collect parseable execution directories grouped by case path.
    4. Persist discovery results, then package and submit each changed case.
    5. In archive mode, settle and persist completed snapshot checkpoints.

Dry runs stop after discovery and emit a summary. Successful ingestions update
database state used to keep future runs idempotent.

Structured log metric definitions for this runner live in
``docs/architecture/metadata-ingestion.md``. This module emits those field names
verbatim in discovery, selection, and run-summary events.
"""

from __future__ import annotations

import hashlib
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from app.features.ingestion.parsers.parser import _locate_metadata_files
from app.scripts.ingestion.archive_client import (
    _authorization_headers,
    _build_archive_checkpoints_endpoint_url,
    _build_discovery_results_endpoint_url,
    _build_state_endpoint_url,
    _fetch_archive_checkpoints,
    _fetch_ingestion_state,
    _http_request_error,
    _normalized_api_base_url,
    _read_json_object_response,
    _timeout_request_error,
    _url_request_error,
)
from app.scripts.ingestion.archive_discovery import _scan_archive
from app.scripts.ingestion.archive_ingestor_core import (
    ArchiveCheckpointPersistenceCallback,
    CaseSubmissionCallback,
    DiscoveryResultsPersistenceCallback,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    IngestorRunReport,
    MetadataLocator,
    SleepCallback,
    _build_config_from_env,
    _log_event,
)
from app.scripts.ingestion.archive_workflow import (
    _finalize_archive_checkpoints,
    _handle_dry_run,
    _handle_ingest_run,
    _log_scan_completed,
    _log_startup_configuration,
    _persist_discovery_results,
    _validate_run_preconditions,
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
            "scan_mode": config.scan_mode,
            "archive_root": str(config.archive_root),
        },
    )
    exit_code = _run_ingestor(config)
    _log_event(
        "run_finished",
        {
            "mode": "dry-run" if config.dry_run else "ingest",
            "scan_mode": config.scan_mode,
            "exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - start_time, 3),
        },
    )
    return exit_code


def _case_submission_callback(
    post_request_fn: CaseSubmissionCallback | None,
) -> CaseSubmissionCallback:
    """Resolve the HPC upload transport for this run."""
    return (
        _post_hpc_upload_ingestion_request
        if post_request_fn is None
        else post_request_fn
    )


def _run_ingestor(
    config: IngestorConfig,
    metadata_locator: MetadataLocator = _locate_metadata_files,
    sleep_fn: SleepCallback = time.sleep,
    post_request_fn: CaseSubmissionCallback | None = None,
    discovery_post_request_fn: DiscoveryResultsPersistenceCallback | None = None,
    checkpoint_post_request_fn: ArchiveCheckpointPersistenceCallback | None = None,
    case_path_filter: Callable[[Path], bool] | None = None,
    additional_dir_pruner: Callable[[str, list[str]], None] | None = None,
    archive_checkpointing: bool = True,
    run_report: IngestorRunReport | None = None,
) -> int:
    """Execute one complete archive scan-and-upload cycle."""
    use_prepared_archives = post_request_fn is None
    post_request_fn = _case_submission_callback(post_request_fn)

    endpoint_url = _build_endpoint_url(config)
    state_endpoint_url = _build_state_endpoint_url(config)
    _log_startup_configuration(
        config,
        endpoint_url=endpoint_url,
        state_endpoint_url=state_endpoint_url,
        log_event_fn=_log_event,
    )

    if not _validate_run_preconditions(config, log_event_fn=_log_event):
        return 1

    completed_snapshot_keys: set[str] = set()
    if config.scan_mode == "archive" and archive_checkpointing:
        try:
            completed_snapshot_keys = _fetch_archive_checkpoints(
                _build_archive_checkpoints_endpoint_url(config),
                config.api_token,
                config.machine_name,
                config.archive_root.name,
                archive_start=config.archive_year_start,
                archive_end=config.archive_year_end,
                timeout_seconds=config.request_timeout_seconds,
            )
        except IngestionRequestError as exc:
            _log_event(
                "archive_checkpoint_fetch_failed",
                {"status_code": exc.status_code, "error": str(exc)},
            )
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

    new_discovery_results: list[ExecutionDiscoveryResult] = []
    try:
        (
            scan_results,
            candidates,
            submission_qualified_case_count,
            discovery_stats,
            snapshot_scan,
        ) = _scan_archive(
            config,
            state,
            metadata_locator=metadata_locator,
            discovery_results=new_discovery_results,
            completed_snapshot_keys=completed_snapshot_keys,
            case_path_filter=case_path_filter,
            additional_dir_pruner=additional_dir_pruner,
            run_report=run_report,
        )
    except Exception as exc:
        _log_event(
            "archive_scan_failed",
            {"error": f"{exc.__class__.__name__}: {exc}"},
        )
        return 1

    _log_scan_completed(
        config,
        scan_results,
        candidates,
        submission_qualified_case_count,
        discovery_stats,
        log_event_fn=_log_event,
    )

    if config.dry_run:
        return _handle_dry_run(
            candidates,
            scan_results,
            submission_qualified_case_count,
            discovery_stats,
            archive_root=config.archive_root,
            log_event_fn=_log_event,
        )

    if not _persist_discovery_results(
        new_discovery_results,
        _build_discovery_results_endpoint_url(config),
        config,
        sleep_fn,
        discovery_post_request_fn,
    ):
        return 1

    ingest_exit_code = _handle_ingest_run(
        candidates,
        scan_results,
        config,
        endpoint_url,
        state,
        submission_qualified_case_count,
        discovery_stats,
        sleep_fn=sleep_fn,
        post_request_fn=post_request_fn,
        log_event_fn=_log_event,
        candidate_preparer=(
            (
                lambda candidate: _prepared_hpc_case_submission(
                    candidate, config.machine_name
                )
            )
            if use_prepared_archives
            else None
        ),
        run_report=run_report,
    )

    if not archive_checkpointing:
        return ingest_exit_code

    if not _finalize_archive_checkpoints(
        snapshot_scan,
        state,
        new_discovery_results,
        _build_archive_checkpoints_endpoint_url(config),
        config,
        sleep_fn,
        checkpoint_post_request_fn,
    ):
        return 1

    return ingest_exit_code


def _build_endpoint_url(config: IngestorConfig) -> str:
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/from-hpc-upload"


def _create_case_archive(
    case_path: str,
    staging_dir: Path,
    selected_execution_ids: list[str] | None = None,
) -> Path:
    """Package selected execution directories under one case directory root.

    ``None`` preserves the legacy full-case helper behavior for direct callers;
    the candidate upload path always supplies selected execution IDs.
    """
    case_dir = Path(case_path).resolve()
    if not case_dir.is_dir():
        raise IngestionRequestError(
            f"Case path is not a directory: {case_path}",
            status_code=None,
            transient=False,
        )

    if selected_execution_ids is None:
        case_hash = hashlib.sha256(case_path.encode("utf-8")).hexdigest()[:12]
        archive_path = staging_dir / f"{case_dir.name or 'case'}-{case_hash}.tar.gz"

        with tarfile.open(archive_path, "w:gz") as tar_file:
            tar_file.add(case_dir, arcname=case_dir.name)

        return archive_path

    if not selected_execution_ids:
        raise IngestionRequestError(
            f"No selected execution directories for case: {case_path}",
            status_code=None,
            transient=False,
        )

    selected_execution_dirs: list[Path] = []
    for execution_id in selected_execution_ids:
        execution_dir = (case_dir / execution_id).resolve()
        if execution_dir.parent != case_dir or not execution_dir.is_dir():
            raise IngestionRequestError(
                f"Selected execution path is not a directory in case: {execution_id}",
                status_code=None,
                transient=False,
            )
        selected_execution_dirs.append(execution_dir)

    case_hash = hashlib.sha256(case_path.encode("utf-8")).hexdigest()[:12]
    archive_path = staging_dir / f"{case_dir.name or 'case'}-{case_hash}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar_file:
        # The parser expects one case basename at archive root.  Add only its
        # directory entry and the executions selected for this candidate.
        tar_file.add(case_dir, arcname=case_dir.name, recursive=False)
        for execution_dir in selected_execution_dirs:
            tar_file.add(execution_dir, arcname=f"{case_dir.name}/{execution_dir.name}")

    return archive_path


@contextmanager
def _prepared_hpc_case_submission(
    candidate: IngestionCandidate,
    machine_name: str,
) -> Iterator[CaseSubmissionCallback]:
    """Stage a candidate once and retain its immutable upload body for retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_started_at = time.monotonic()
        staged_archive = _create_case_archive(
            candidate.case_path,
            Path(tmpdir),
            candidate.new_execution_ids,
        )
        body, boundary = _encode_multipart_form_data(
            archive_path=staged_archive,
            machine_name=machine_name,
            case_path=candidate.case_path,
            processed_execution_ids=candidate.new_execution_ids,
        )
        _log_event(
            "archive_created",
            {
                "case_path": candidate.case_path,
                "selected_execution_count": len(candidate.new_execution_ids),
                "archive_bytes": staged_archive.stat().st_size,
                "duration_seconds": round(time.monotonic() - archive_started_at, 3),
            },
        )
        attempt = 0

        def submit(
            endpoint_url: str,
            api_token: str,
            _archive_path: str,
            machine_name: str,
            *,
            processed_execution_ids: list[str],
            timeout_seconds: int,
        ) -> IngestionRequestResponse:
            """Submit the prebuilt body without rebuilding its archive or boundary."""
            del _archive_path, machine_name, processed_execution_ids
            nonlocal attempt
            attempt += 1
            upload_started_at = time.monotonic()
            try:
                return _send_hpc_upload_request(
                    endpoint_url, api_token, body, boundary, timeout_seconds
                )
            finally:
                _log_event(
                    "case_upload_attempt",
                    {
                        "case_path": candidate.case_path,
                        "attempt": attempt,
                        "archive_bytes": staged_archive.stat().st_size,
                        "duration_seconds": round(
                            time.monotonic() - upload_started_at, 3
                        ),
                    },
                )

        yield submit


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

    _append_multipart_text_part(body, boundary, "machine_name", machine_name)
    _append_multipart_text_part(body, boundary, "case_path", case_path)
    for execution_id in processed_execution_ids:
        _append_multipart_text_part(
            body,
            boundary,
            "processed_execution_ids",
            execution_id,
        )

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


def _append_multipart_text_part(
    body: bytearray,
    boundary: str,
    name: str,
    value: str,
) -> None:
    """Append one UTF-8 text field to a multipart request buffer."""
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
    )
    body.extend(value.encode("utf-8"))
    body.extend(b"\r\n")


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
        staged_archive = _create_case_archive(
            archive_path, Path(tmpdir), processed_execution_ids
        )
        body, boundary = _encode_multipart_form_data(
            archive_path=staged_archive,
            machine_name=machine_name,
            case_path=archive_path,
            processed_execution_ids=processed_execution_ids,
        )

        return _send_hpc_upload_request(
            endpoint_url, api_token, body, boundary, timeout_seconds
        )


def _send_hpc_upload_request(
    endpoint_url: str,
    api_token: str,
    body: bytes,
    boundary: str,
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """Send one already-encoded HPC archive upload request."""
    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            **_authorization_headers(api_token),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            parsed_body = _read_json_object_response(response)
            return {"status_code": response.status, "body": parsed_body}
    except urllib.error.HTTPError as exc:
        raise _http_request_error(exc) from exc
    except urllib.error.URLError as exc:
        raise _url_request_error(exc) from exc
    except TimeoutError as exc:
        raise _timeout_request_error() from exc


if __name__ == "__main__":
    raise SystemExit(main())
