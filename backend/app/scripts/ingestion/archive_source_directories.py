"""Record source paths visited by normal ingestion, including skipped uploads."""

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.common.utils import _normalize_hpc_username
from app.features.catalog.enums import SourceDirectoryKind
from app.features.ingestion.parsers.parser import (
    _locate_metadata_files,
    _parse_all_files,
)
from app.features.ingestion.schemas import SourceDirectoryObservation
from app.features.machine.utils import parse_machine_name
from app.scripts.ingestion.archive_client import (
    _build_json_request,
    _http_request_error,
    _normalized_api_base_url,
    _read_json_object_response,
    _retry_backoff_seconds,
    _timeout_request_error,
    _url_request_error,
)
from app.scripts.ingestion.archive_discovery import _build_processed_ids_by_key
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_RESULT_BATCH_SIZE,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    SleepCallback,
    _log_event,
)
from app.scripts.ingestion.archive_layout import _case_identity_key

SourceDirectoryPost = Callable[..., IngestionRequestResponse]


def _observe_source_directory(
    case_path: Path,
    execution_dirname: str,
    config: IngestorConfig,
    hpc_username: str | None = None,
) -> SourceDirectoryObservation:
    """Read actual execution metadata rather than infer identity from paths."""
    execution_path = case_path / execution_dirname
    parsed = _parse_all_files(
        str(execution_path), _locate_metadata_files(str(execution_path))
    )
    parsed_machine, _ = parse_machine_name(parsed.machine or "")
    configured_machine, _ = parse_machine_name(config.machine_name)
    if parsed_machine != configured_machine:
        raise ValueError(
            f"Source machine does not match configured machine: {execution_path}"
        )
    return SourceDirectoryObservation(
        case_name=parsed.case_name or "",
        hpc_username=_normalize_hpc_username(parsed.hpc_username)
        or _normalize_hpc_username(hpc_username)
        or "",
        execution_id=parsed.execution_id,
        kind=SourceDirectoryKind(config.scan_mode),
        case_path=str(case_path),
        execution_path=str(execution_path),
    )


def _persist_visited_source_directories(
    visited: list[tuple[Path, str]],
    state: dict[str, Any],
    config: IngestorConfig,
    sleep_fn: SleepCallback,
    post_request_fn: SourceDirectoryPost | None = None,
    hpc_username_resolver: Callable[[IngestionCandidate], str | None] | None = None,
) -> bool:
    """Persist only visited executions known to be ingested, before checkpoints."""
    processed = _build_processed_ids_by_key(
        state,
        scan_mode=config.scan_mode,
        staging_root_basename=config.archive_root.name,
    )
    observations = []
    for case_path, execution_dirname in sorted(set(visited)):
        identity = _case_identity_key(
            str(case_path.resolve()),
            config.scan_mode,
            staging_root_basename=config.archive_root.name,
        )
        if execution_dirname not in processed[identity]:
            # Deferred, failed, or rejected-only discoveries have no owner yet.
            continue
        try:
            hpc_username = None
            if hpc_username_resolver is not None:
                hpc_username = hpc_username_resolver(
                    IngestionCandidate(
                        case_path=str(case_path),
                        execution_ids=[execution_dirname],
                        new_execution_ids=[],
                        fingerprint="",
                    )
                )
            observations.append(
                _observe_source_directory(
                    case_path, execution_dirname, config, hpc_username
                )
            )
        except (ValueError, OSError) as exc:
            _log_event(
                "source_directory_unresolved",
                {
                    "execution_path": str(case_path / execution_dirname),
                    "error": str(exc),
                },
            )
            return False

    post_request_fn = post_request_fn or _post_source_directories_request
    endpoint = (
        f"{_normalized_api_base_url(config.api_base_url)}/ingestions/source-directories"
    )
    for offset in range(0, len(observations), DISCOVERY_RESULT_BATCH_SIZE):
        batch = observations[offset : offset + DISCOVERY_RESULT_BATCH_SIZE]
        for attempt in range(1, config.max_attempts + 1):
            try:
                response = post_request_fn(
                    endpoint,
                    config.api_token,
                    config.machine_name,
                    directories=batch,
                    timeout_seconds=config.request_timeout_seconds,
                )
                for unresolved in response.get("body", {}).get("unresolved", []):
                    _log_event(
                        "source_directory_unresolved",
                        {
                            "execution_path": unresolved["execution_path"],
                            "error": "No matching ingested case and execution",
                        },
                    )
                break
            except IngestionRequestError as exc:
                _log_event(
                    "source_directory_persistence_failed",
                    {"attempt": attempt, "error": str(exc)},
                )
                if not exc.transient or attempt == config.max_attempts:
                    return False
                sleep_fn(_retry_backoff_seconds(attempt))
    return True


def _post_source_directories_request(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    directories: list[SourceDirectoryObservation],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    request = _build_json_request(
        endpoint_url,
        api_token,
        {
            "machine_name": machine_name,
            "directories": [
                directory.model_dump(mode="json") for directory in directories
            ],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return {
                "status_code": response.status,
                "body": _read_json_object_response(response),
            }
    except urllib.error.HTTPError as exc:
        raise _http_request_error(exc) from exc
    except urllib.error.URLError as exc:
        raise _url_request_error(exc) from exc
    except TimeoutError as exc:
        raise _timeout_request_error() from exc
