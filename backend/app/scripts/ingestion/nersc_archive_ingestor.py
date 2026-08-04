"""Scan NERSC archives and trigger SimBoard path-based ingestion.

This script is intended for scheduled execution (for example, a CronJob)
against a bind-mounted performance archive. Runtime configuration is read
from environment variables (for example ``SIMBOARD_API_BASE_URL``,
``SIMBOARD_API_TOKEN``, ``PERF_ARCHIVE_ROOT``, ``OLD_PERF_ARCHIVE_ROOT``, and ``DRY_RUN``).

Each run executes four phases:

  1. Discover and collect parseable execution directories grouped by case path.
  2. Fetch persisted per-case state from SimBoard API.
  3. Submit one ingestion request per changed case with retry/backoff.
  4. Rely on DB writes from successful ingestions for future idempotent runs.

Structured log metric definitions for this runner live in
``docs/architecture/metadata-ingestion.md``. This module emits those field names
verbatim in discovery, selection, and run-summary events.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any, Callable

from app.api.version import API_BASE
from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
    _locate_metadata_files,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DEFAULT_PERF_ARCHIVE_ROOT,
    DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES,
    DISCOVERY_RESULT_BATCH_SIZE,
    MAX_DRY_RUN_CANDIDATE_LOGS,
    STATE_VERSION,
    ArchiveSnapshotScan,
    CaseCollectionLogData,
    CaseScanResult,
    DiscoveryStats,
    ExecutionCollectionDecision,
    ExecutionDiscoveryResult,
    IngestionAttemptResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    UnsupportedArchiveLayoutError,
    _build_config_from_env,
    _build_discovery_results_by_key,
    _case_log_label,
    _case_state_processed_ids,
    _compute_case_fingerprint,
    _deduplicate_discovery_results,
    _is_transient_status,
    _log_event,
    _log_startup_configuration,
    _record_successful_case,
    _utc_now_iso,
)
from app.scripts.ingestion.archive_layout import (
    _build_case_path_filter,
    _build_walk_dir_filter,
    _case_identity_key,
    _enumerate_archive_snapshot_keys,
    _record_archive_snapshot_reference,
)

EXECUTION_DIR_PATTERN = re.compile(r"\d+\.\d+-\d+$")


def main() -> int:
    """Build runtime configuration and execute the ingestion runner.

    Returns
    -------
    int
        Process exit code (``0`` success, ``1`` failure).
    """
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


def _run_ingestor(  # noqa: C901
    config: IngestorConfig,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    sleep_fn: Callable[[float], None] = time.sleep,
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
    discovery_post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
    checkpoint_post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> int:
    """Execute one complete archive scan-and-ingest cycle.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.
    metadata_locator : Callable[[str], object], optional
        Validation callable used when scanning execution directories.
    sleep_fn : Callable[[float], None], optional
        Sleep function used for retry backoff.

    Returns
    -------
    int
        Process exit code (``0`` success, ``1`` failure).
    """
    if post_request_fn is None:
        post_request_fn = _post_ingestion_request

    endpoint_url = _build_endpoint_url(config)
    state_endpoint_url = _build_state_endpoint_url(config)
    _log_startup_configuration(
        config, endpoint_url=endpoint_url, state_endpoint_url=state_endpoint_url
    )

    if not config.archive_root.is_dir():
        _log_event("archive_root_missing", {"archive_root": str(config.archive_root)})
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

    completed_snapshot_keys: set[str] = set()
    if config.scan_mode == "archive":
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
        )
    except UnsupportedArchiveLayoutError as exc:
        _log_event("configuration_error", {"error": str(exc)})
        return 1
    except Exception as exc:
        _log_event(
            "archive_scan_failed",
            {"error": f"{exc.__class__.__name__}: {exc}"},
        )
        return 1

    _log_event(
        "scan_completed",
        {
            "scan_mode": config.scan_mode,
            "archive_root": str(config.archive_root),
            "discovered_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
            "skipped_transient": discovery_stats["skipped_transient"],
            "accepted_execution_ids": discovery_stats["accepted_execution_ids"],
            "rejected_existing_execution_ids": discovery_stats[
                "rejected_existing_execution_ids"
            ],
            "rejected_incomplete_execution_ids": discovery_stats[
                "rejected_incomplete_execution_ids"
            ],
            "rejected_invalid_execution_ids": discovery_stats[
                "rejected_invalid_execution_ids"
            ],
            "transient_execution_ids": discovery_stats["transient_execution_ids"],
            "deferred_execution_ids": discovery_stats["deferred_execution_ids"],
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

    discovery_endpoint_url = _build_discovery_results_endpoint_url(config)
    if not _persist_discovery_results_with_retries(
        new_discovery_results,
        discovery_endpoint_url,
        config.api_token,
        config.machine_name,
        max_attempts=config.max_attempts,
        timeout_seconds=config.request_timeout_seconds,
        sleep_fn=sleep_fn,
        post_request_fn=discovery_post_request_fn,
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
    )
    if config.scan_mode != "archive":
        return ingest_exit_code

    settled_snapshot_keys = _settled_archive_snapshot_keys(
        snapshot_scan,
        state,
        new_discovery_results,
    )
    if not _persist_archive_checkpoints_with_retries(
        settled_snapshot_keys,
        _build_archive_checkpoints_endpoint_url(config),
        config.api_token,
        config.machine_name,
        snapshot_scan.archive_name,
        max_attempts=config.max_attempts,
        timeout_seconds=config.request_timeout_seconds,
        sleep_fn=sleep_fn,
        post_request_fn=checkpoint_post_request_fn,
    ):
        return 1
    return ingest_exit_code


def _build_endpoint_url(config: IngestorConfig) -> str:
    """Build the path-based ingestion endpoint URL from runtime config.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.

    Returns
    -------
    str
        Fully qualified ingestion endpoint URL.
    """
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/from-path"


def _build_state_endpoint_url(config: IngestorConfig) -> str:
    """Build the ingestion-state endpoint URL from runtime config."""
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/state"


def _build_discovery_results_endpoint_url(config: IngestorConfig) -> str:
    """Build discovery-result persistence endpoint URL."""
    return (
        f"{_normalized_api_base_url(config.api_base_url)}/ingestions/discovery-results"
    )


def _build_archive_checkpoints_endpoint_url(config: IngestorConfig) -> str:
    """Build archive checkpoint read/write endpoint URL."""
    return f"{_normalized_api_base_url(config.api_base_url)}/ingestions/archive-checkpoints"


# Archive Discovery
# -----------------


def _scan_archive(
    config: IngestorConfig,
    state: dict[str, Any],
    metadata_locator: Callable[[str], object],
    discovery_results: list[ExecutionDiscoveryResult] | None = None,
    completed_snapshot_keys: set[str] | None = None,
) -> tuple[
    list[CaseScanResult],
    list[IngestionCandidate],
    int,
    DiscoveryStats,
    ArchiveSnapshotScan,
]:
    """Compute scan results, candidates, and discovery counters.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.
    metadata_locator : Callable[[str], object]
        Validation callable used during execution discovery.

    Returns
    -------
    tuple[
        list[CaseScanResult],
        list[IngestionCandidate],
        int,
        DiscoveryStats,
    ]
        Scan results, selected candidate list, submission-qualified case count,
        and discovery counters
    """
    case_collection_data: dict[str, CaseCollectionLogData] = {}
    discovery_stats = _new_discovery_stats()
    staging_root_basename = (
        config.archive_root.name or Path(DEFAULT_PERF_ARCHIVE_ROOT).name
    )
    case_path_filter = _build_case_path_filter(config)
    snapshot_scan = ArchiveSnapshotScan(archive_name=config.archive_root.name)

    if config.scan_mode == "archive":
        snapshot_scan.eligible_keys = _enumerate_archive_snapshot_keys(config)
        snapshot_scan.completed_keys = (
            set() if completed_snapshot_keys is None else completed_snapshot_keys
        ) & snapshot_scan.eligible_keys

    selected_snapshot_keys = snapshot_scan.eligible_keys - snapshot_scan.completed_keys
    walk_dir_filter = _build_walk_dir_filter(
        config,
        selected_snapshot_keys=(
            selected_snapshot_keys
            if config.scan_mode == "archive" and snapshot_scan.eligible_keys
            else None
        ),
    )
    processed_ids_by_key = _build_processed_ids_by_key(
        state,
        scan_mode=config.scan_mode,
        staging_root_basename=staging_root_basename,
    )

    def handle_walk_error(exc: OSError) -> None:
        snapshot_scan.traversal_complete = False
        _log_event(
            "archive_scan_failed",
            {
                "scan_mode": config.scan_mode,
                "archive_root": str(config.archive_root),
                "error": f"{exc.__class__.__name__}: {exc}",
            },
        )

    grouped_executions = _discover_case_executions(
        config.archive_root,
        metadata_locator,
        discovery_stats,
        case_collection_data,
        case_path_filter=case_path_filter,
        walk_dir_filter=walk_dir_filter,
        scan_mode=config.scan_mode,
        processed_ids_by_key=processed_ids_by_key,
        discovery_results=discovery_results,
        discovery_results_by_key=_build_discovery_results_by_key(state),
        staging_root_basename=staging_root_basename,
        walk_error_handler=(
            handle_walk_error if config.scan_mode == "archive" else None
        ),
        execution_observer=(
            partial(
                _record_archive_snapshot_reference,
                archive_root=config.archive_root.resolve(),
                references_by_key=snapshot_scan.references_by_key,
            )
            if config.scan_mode == "archive"
            else None
        ),
    )
    scan_results = _build_case_scan_results(grouped_executions)
    all_candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode=config.scan_mode,
        staging_root_basename=staging_root_basename,
    )
    candidates = (
        all_candidates
        if config.max_cases_per_run is None
        else all_candidates[: config.max_cases_per_run]
    )
    _log_execution_collection_outcomes(
        case_collection_data,
        state,
        candidates,
        discovery_stats,
        archive_root=config.archive_root,
        scan_mode=config.scan_mode,
        staging_root_basename=staging_root_basename,
    )

    return (
        scan_results,
        candidates,
        len(all_candidates),
        discovery_stats,
        snapshot_scan,
    )


def _discover_case_executions(
    archive_root: Path,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    stats: DiscoveryStats | None = None,
    case_collection_data: dict[str, CaseCollectionLogData] | None = None,
    *,
    case_path_filter: Callable[[Path], bool] | None = None,
    walk_dir_filter: Callable[[str, list[str]], None] | None = None,
    scan_mode: str = "staging",
    processed_ids_by_key: defaultdict[str, set[str]] | None = None,
    staging_root_basename: str = Path(DEFAULT_PERF_ARCHIVE_ROOT).name,
    discovery_results: list[ExecutionDiscoveryResult] | None = None,
    discovery_results_by_key: dict[tuple[str, str], str] | None = None,
    execution_observer: Callable[[Path, str], None] | None = None,
    walk_error_handler: Callable[[OSError], None] | None = None,
) -> dict[str, list[str]]:
    """Discover parseable execution IDs grouped by case path.

    Parameters
    ----------
    archive_root : Path
        Root path of the mounted performance archive.
    metadata_locator : Callable[[str], object], optional
        Callable used to validate that an execution directory contains
        the required metadata files.
    stats : dict[str, int] | None, optional
        Mutable counter dictionary populated with discovery metrics:
        ``execution_dirs_scanned``, ``execution_dirs_accepted``,
        ``skipped_incomplete``, and ``skipped_invalid``.
    case_collection_data : dict[str, CaseCollectionLogData] | None, optional
        Mutable case-level logging records populated during discovery so later
        logging can include rejected-only cases.

    Returns
    -------
    dict[str, list[str]]
        Mapping of absolute case directory paths to sorted execution IDs.
    """
    grouped: dict[str, set[str]] = {}
    effective_stats = stats if stats is not None else _new_discovery_stats()
    _initialize_discovery_stats(effective_stats)
    scan_started_at = time.monotonic()
    directories_visited = 0
    archive_root_str = str(archive_root)
    current_dir = archive_root_str

    _log_event(
        "archive_scan_started",
        {"scan_mode": scan_mode, "archive_root": archive_root_str},
    )

    for dirpath, dirnames, _ in os.walk(archive_root, onerror=walk_error_handler):
        directories_visited += 1
        current_dir = dirpath

        if walk_dir_filter is not None:
            walk_dir_filter(dirpath, dirnames)
        case_dir = Path(dirpath)

        for dirname in dirnames:
            if not EXECUTION_DIR_PATTERN.fullmatch(dirname):
                continue
            if case_path_filter is not None and not case_path_filter(case_dir):
                continue
            if execution_observer is not None:
                execution_observer(case_dir, dirname)

            _collect_case_execution(
                grouped,
                case_dir,
                dirname,
                metadata_locator=metadata_locator,
                stats=effective_stats,
                case_collection_data=case_collection_data,
                processed_ids_by_key=processed_ids_by_key,
                scan_mode=scan_mode,
                staging_root_basename=staging_root_basename,
                discovery_results=discovery_results,
                discovery_results_by_key=discovery_results_by_key,
            )

        if directories_visited % DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES == 0:
            _log_archive_scan_progress(
                event="archive_scan_progress",
                archive_root=archive_root_str,
                current_dir=dirpath,
                directories_visited=directories_visited,
                grouped=grouped,
                stats=effective_stats,
                started_at=scan_started_at,
                scan_mode=scan_mode,
            )

    _log_archive_scan_progress(
        event="archive_scan_completed",
        archive_root=archive_root_str,
        current_dir=current_dir,
        directories_visited=directories_visited,
        grouped=grouped,
        stats=effective_stats,
        started_at=scan_started_at,
        scan_mode=scan_mode,
    )

    return {case_path: sorted(exec_ids) for case_path, exec_ids in grouped.items()}


def _log_archive_scan_progress(
    *,
    event: str,
    archive_root: str,
    current_dir: str,
    directories_visited: int,
    grouped: dict[str, set[str]],
    stats: DiscoveryStats | None,
    started_at: float,
    scan_mode: str,
) -> None:
    """Emit a structured archive-scan progress or completion log."""
    _log_event(
        event,
        {
            "scan_mode": scan_mode,
            "archive_root": archive_root,
            "current_dir": current_dir,
            "directories_visited": directories_visited,
            "discovered_cases": len(grouped),
            "execution_dirs_scanned": (
                0 if stats is None else stats["execution_dirs_scanned"]
            ),
            "execution_dirs_accepted": (
                0 if stats is None else stats["execution_dirs_accepted"]
            ),
            "skipped_transient": (0 if stats is None else stats["skipped_transient"]),
            "rejected_existing_execution_ids": (
                0 if stats is None else stats["rejected_existing_execution_ids"]
            ),
            "duration_seconds": round(time.monotonic() - started_at, 3),
        },
    )


def _initialize_discovery_stats(stats: DiscoveryStats | None) -> None:
    """Ensure discovery stats dictionary contains expected keys."""
    if stats is None:
        return

    stats.setdefault("execution_dirs_scanned", 0)
    stats.setdefault("execution_dirs_accepted", 0)
    stats.setdefault("skipped_incomplete", 0)
    stats.setdefault("skipped_invalid", 0)
    stats.setdefault("skipped_transient", 0)
    stats.setdefault("accepted_execution_ids", 0)
    stats.setdefault("rejected_existing_execution_ids", 0)
    stats.setdefault("rejected_incomplete_execution_ids", 0)
    stats.setdefault("rejected_invalid_execution_ids", 0)
    stats.setdefault("transient_execution_ids", 0)
    stats.setdefault("deferred_execution_ids", 0)


def _collect_case_execution(  # noqa: C901
    grouped: dict[str, set[str]],
    case_dir: Path,
    execution_id: str,
    *,
    metadata_locator: Callable[[str], object],
    stats: DiscoveryStats | None,
    case_collection_data: dict[str, CaseCollectionLogData] | None,
    processed_ids_by_key: defaultdict[str, set[str]] | None,
    scan_mode: str,
    staging_root_basename: str,
    discovery_results: list[ExecutionDiscoveryResult] | None = None,
    discovery_results_by_key: dict[tuple[str, str], str] | None = None,
) -> None:
    """Validate and record one discovered execution directory."""
    case_path = str(case_dir.resolve())
    log_data = _get_case_collection_log_data(case_path, case_collection_data)
    if log_data is not None:
        log_data.execution_count_total += 1

    case_identity_key = _case_identity_key(
        case_path,
        scan_mode,
        staging_root_basename=staging_root_basename,
    )
    known_processed_ids = (
        set()
        if processed_ids_by_key is None
        else processed_ids_by_key[case_identity_key]
    )
    if execution_id in known_processed_ids:
        if stats is not None:
            stats["rejected_existing_execution_ids"] += 1
        if log_data is not None:
            log_data.rejected_decisions.append(
                ExecutionCollectionDecision(
                    case_path=case_path,
                    execution_id=execution_id,
                    decision="rejected",
                    reason="already_processed",
                )
            )

        return

    stored_outcome = (
        None
        if discovery_results_by_key is None
        else discovery_results_by_key.get((case_identity_key, execution_id))
    )
    if stored_outcome == "accepted":
        if stats is not None:
            stats["execution_dirs_accepted"] += 1

        grouped.setdefault(case_path, set()).add(execution_id)

        if log_data is not None:
            log_data.valid_execution_ids.add(execution_id)

        return
    if stored_outcome in {"rejected_incomplete", "rejected_invalid"}:
        reason = "incomplete" if stored_outcome == "rejected_incomplete" else "invalid"

        if stats is not None:
            stats[f"skipped_{reason}"] += 1  # type: ignore[literal-required]
            stats[f"rejected_{reason}_execution_ids"] += 1  # type: ignore[literal-required]

        if log_data is not None:
            log_data.rejected_decisions.append(
                ExecutionCollectionDecision(
                    case_path=case_path,
                    execution_id=execution_id,
                    decision="rejected",
                    reason=reason,
                    detail="stored_discovery_result",
                )
            )

        return

    if stats is not None:
        stats["execution_dirs_scanned"] += 1

    rejection_decision = _validate_execution_dir(
        case_dir,
        execution_id,
        metadata_locator=metadata_locator,
        stats=stats,
    )
    if rejection_decision is not None:
        if discovery_results is not None and rejection_decision.reason in {
            "incomplete",
            "invalid",
        }:
            discovery_results.append(
                ExecutionDiscoveryResult(
                    case_identity=case_identity_key,
                    execution_id=execution_id,
                    outcome=(
                        "rejected_incomplete"
                        if rejection_decision.reason == "incomplete"
                        else "rejected_invalid"
                    ),
                )
            )
        if log_data is not None:
            log_data.rejected_decisions.append(rejection_decision)

        return

    if stats is not None:
        stats["execution_dirs_accepted"] += 1

    if discovery_results is not None:
        discovery_results.append(
            ExecutionDiscoveryResult(
                case_identity=case_identity_key,
                execution_id=execution_id,
                outcome="accepted",
            )
        )

    grouped.setdefault(case_path, set()).add(execution_id)
    if log_data is not None:
        log_data.valid_execution_ids.add(execution_id)


def _get_case_collection_log_data(
    case_path: str,
    case_collection_data: dict[str, CaseCollectionLogData] | None,
) -> CaseCollectionLogData | None:
    """Return mutable case discovery log record when collection logging is enabled."""
    if case_collection_data is None:
        return None

    return case_collection_data.setdefault(
        case_path,
        CaseCollectionLogData(case_path=case_path),
    )


def _validate_execution_dir(
    case_dir: Path,
    execution_id: str,
    metadata_locator: Callable[[str], object],
    stats: DiscoveryStats | None,
) -> ExecutionCollectionDecision | None:
    """Validate execution directory metadata and return rejection details.

    Parameters
    ----------
    case_dir : Path
        Case directory containing the execution subdirectory.
    execution_id : str
        Execution directory name.
    metadata_locator : Callable[[str], object]
        Callable used to validate execution metadata files.
    stats : dict[str, int] | None
        Optional discovery stats accumulator.
    Returns
    -------
    ExecutionCollectionDecision | None
        ``None`` when execution metadata is valid; otherwise structured
        rejection details for canonical execution-decision logging.
    """
    execution_dir = case_dir / execution_id

    try:
        metadata_locator(str(execution_dir))

        return None
    except IncompleteArchiveError as exc:
        if stats is not None:
            stats["skipped_incomplete"] += 1
            stats["rejected_incomplete_execution_ids"] += 1

        return _build_rejected_execution_decision(
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            reason="incomplete",
            exc=exc,
        )
    except ArchiveValidationError as exc:
        if stats is not None:
            stats["skipped_invalid"] += 1
            stats["rejected_invalid_execution_ids"] += 1

        return _build_rejected_execution_decision(
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            reason="invalid",
            exc=exc,
        )
    except OSError as exc:
        if stats is not None:
            stats["skipped_transient"] += 1
            stats["transient_execution_ids"] += 1

        return _build_rejected_execution_decision(
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            reason="transient",
            exc=exc,
        )


def _log_execution_collection_outcomes(
    case_collection_data: dict[str, CaseCollectionLogData],
    state: dict[str, Any],
    candidates: list[IngestionCandidate],
    discovery_stats: DiscoveryStats,
    *,
    archive_root: Path,
    scan_mode: str = "staging",
    staging_root_basename: str = Path(DEFAULT_PERF_ARCHIVE_ROOT).name,
) -> None:
    """Emit one contiguous decision block for each discovered case."""
    processed_ids_by_key = _build_processed_ids_by_key(
        state,
        scan_mode=scan_mode,
        staging_root_basename=staging_root_basename,
    )
    selected_new_ids_by_case = {
        candidate.case_path: set(candidate.new_execution_ids)
        for candidate in candidates
    }

    for case_path in sorted(case_collection_data):
        log_data = case_collection_data[case_path]
        case_label = _case_log_label(case_path, archive_root)
        processed_ids = processed_ids_by_key[
            _case_identity_key(
                case_path,
                scan_mode,
                staging_root_basename=staging_root_basename,
            )
        ]
        valid_execution_ids = sorted(log_data.valid_execution_ids)
        existing_rejected_ids = {
            decision.execution_id
            for decision in log_data.rejected_decisions
            if decision.reason == "already_processed"
        }
        new_ids = set(valid_execution_ids) - processed_ids
        selected_new_ids = selected_new_ids_by_case.get(case_path, set())
        existing_ids = sorted(
            existing_rejected_ids | (set(valid_execution_ids) & processed_ids)
        )
        deferred_ids = sorted(new_ids - selected_new_ids)
        rejected_incomplete = sum(
            1
            for decision in log_data.rejected_decisions
            if decision.reason == "incomplete"
        )
        rejected_invalid = sum(
            1
            for decision in log_data.rejected_decisions
            if decision.reason == "invalid"
        )
        transient = sum(
            1
            for decision in log_data.rejected_decisions
            if decision.reason == "transient"
        )

        _log_event(
            "case_collection_begin",
            {
                "case": case_label,
                "execution_count_total": log_data.execution_count_total,
                "execution_count_valid": len(valid_execution_ids),
                "execution_count_rejected_incomplete": rejected_incomplete,
                "execution_count_rejected_invalid": rejected_invalid,
                "execution_count_transient": transient,
                "execution_count_existing": len(existing_ids),
                "execution_count_new": len(new_ids),
                "execution_count_selected_new": len(selected_new_ids),
                "execution_count_deferred": len(deferred_ids),
            },
        )

        decisions_by_execution_id = {
            decision.execution_id: decision for decision in log_data.rejected_decisions
        }

        for execution_id in valid_execution_ids:
            if execution_id in existing_rejected_ids:
                continue

            if execution_id in processed_ids:
                discovery_stats["rejected_existing_execution_ids"] += 1
                decisions_by_execution_id[execution_id] = ExecutionCollectionDecision(
                    case_path=case_path,
                    execution_id=execution_id,
                    decision="rejected",
                    reason="already_processed",
                )
                continue

            if execution_id in selected_new_ids:
                discovery_stats["accepted_execution_ids"] += 1
                decisions_by_execution_id[execution_id] = ExecutionCollectionDecision(
                    case_path=case_path,
                    execution_id=execution_id,
                    decision="accepted",
                    reason="new_execution",
                )
                continue

            if execution_id in new_ids:
                discovery_stats["deferred_execution_ids"] += 1
                decisions_by_execution_id[execution_id] = ExecutionCollectionDecision(
                    case_path=case_path,
                    execution_id=execution_id,
                    decision="deferred",
                    reason="max_cases_per_run",
                )

        for execution_id in sorted(decisions_by_execution_id):
            _log_execution_collection_decision(
                decisions_by_execution_id[execution_id],
                case=case_label,
            )

        _log_event(
            "case_collection_summary",
            {
                "case": case_label,
                "accepted": len(selected_new_ids),
                "rejected_existing": len(existing_ids),
                "rejected_incomplete": rejected_incomplete,
                "rejected_invalid": rejected_invalid,
                "transient": transient,
                "deferred": len(deferred_ids),
            },
        )
        processed_ids.update(valid_execution_ids)


def _log_execution_collection_decision(
    decision: ExecutionCollectionDecision,
    *,
    case: str | None = None,
) -> None:
    """Emit one normalized collection outcome for an execution directory."""
    _log_event("execution_collection_decision", decision.to_log_fields(case=case))


def _build_rejected_execution_decision(
    case_path: str,
    execution_id: str,
    reason: str,
    exc: BaseException,
) -> ExecutionCollectionDecision:
    """Build structured rejection metadata for canonical execution logging."""
    return ExecutionCollectionDecision(
        case_path=case_path,
        execution_id=execution_id,
        decision="rejected",
        reason=reason,
        **_compact_rejection_metadata(exc),
    )


def _compact_rejection_metadata(exc: BaseException) -> dict[str, Any]:
    """Build compact structured metadata for one rejection exception."""
    if isinstance(exc, (IncompleteArchiveError, ArchiveValidationError)):
        return _compact_structured_parser_errors(exc)

    detail = str(exc)
    if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError):
        detail = f"{exc.__class__.__name__}: {exc}"

    return {"detail": detail}


def _compact_structured_parser_errors(
    exc: IncompleteArchiveError | ArchiveValidationError,
) -> dict[str, Any]:
    """Build compact metadata from parser-provided structured error payloads."""
    errors = getattr(exc, "errors", [])
    if not isinstance(errors, list) or not errors:
        return {"detail": str(exc)}

    error_codes = sorted(
        {
            code
            for error in errors
            if isinstance(error, dict)
            for code in [error.get("code")]
            if isinstance(code, str)
        }
    )
    missing_file_specs = sorted(
        {
            file_spec
            for error in errors
            if isinstance(error, dict) and error.get("code") == "missing_required_file"
            for file_spec in [error.get("file_spec")]
            if isinstance(file_spec, str)
        }
    )

    metadata: dict[str, Any] = {"error_count": len(errors)}
    if error_codes:
        metadata["error_codes"] = error_codes
    if missing_file_specs:
        metadata["missing_file_specs"] = missing_file_specs

    return metadata


# Archive Path Filters and Layout
# -------------------------------


def _build_case_scan_results(
    grouped_executions: dict[str, list[str]],
) -> list[CaseScanResult]:
    """Build deterministic scan results with execution fingerprints.

    Parameters
    ----------
    grouped_executions : dict[str, list[str]]
        Case-path to execution-ID mapping from discovery.

    Returns
    -------
    list[CaseScanResult]
        Sorted case scan results with normalized execution IDs.
    """
    results: list[CaseScanResult] = []

    for case_path in sorted(grouped_executions):
        execution_ids = sorted(set(grouped_executions[case_path]))
        if not execution_ids:
            continue

        results.append(
            CaseScanResult(
                case_path=case_path,
                execution_ids=execution_ids,
                fingerprint=_compute_case_fingerprint(execution_ids),
            )
        )

    return results


def _settled_archive_snapshot_keys(
    snapshot_scan: ArchiveSnapshotScan,
    state: dict[str, Any],
    new_discovery_results: list[ExecutionDiscoveryResult],
) -> set[str]:
    """Return scanned snapshots whose executions are all permanently resolved."""
    if not snapshot_scan.traversal_complete:
        return set()

    processed_ids = _build_processed_ids_by_key(state, scan_mode="archive")
    outcomes = _build_discovery_results_by_key(state)
    outcomes.update(
        {
            (result.case_identity, result.execution_id): result.outcome
            for result in _deduplicate_discovery_results(new_discovery_results)
        }
    )
    selected_keys = snapshot_scan.eligible_keys - snapshot_scan.completed_keys

    return {
        snapshot_key
        for snapshot_key in selected_keys
        if all(
            execution_id in processed_ids[case_identity]
            or outcomes.get((case_identity, execution_id))
            in {"rejected_incomplete", "rejected_invalid"}
            for case_identity, execution_id in snapshot_scan.references_by_key.get(
                snapshot_key, set()
            )
        )
    }


def _build_processed_ids_by_key(
    state: dict[str, Any],
    *,
    scan_mode: str,
    staging_root_basename: str = Path(DEFAULT_PERF_ARCHIVE_ROOT).name,
) -> defaultdict[str, set[str]]:
    """Aggregate processed execution IDs under normalized case identity keys."""
    case_state = state.get("cases", {})
    if not isinstance(case_state, dict):
        case_state = {}

    processed_ids_by_key: defaultdict[str, set[str]] = defaultdict(set)
    for case_path, current_case_state in case_state.items():
        if not isinstance(case_path, str) or not isinstance(current_case_state, dict):
            continue

        processed_ids_by_key[
            _case_identity_key(
                case_path,
                scan_mode,
                staging_root_basename=staging_root_basename,
            )
        ].update(_case_state_processed_ids(current_case_state))

    return processed_ids_by_key


def _build_ingestion_candidates(
    scan_results: list[CaseScanResult],
    state: dict[str, Any],
    max_cases_per_run: int | None,
    *,
    scan_mode: str = "staging",
    staging_root_basename: str = Path(DEFAULT_PERF_ARCHIVE_ROOT).name,
) -> list[IngestionCandidate]:
    """Select cases that contain newly observed execution IDs.

    Parameters
    ----------
    scan_results : list[CaseScanResult]
        Discovered case results from the current archive scan.
    state : dict[str, Any]
        Persisted runner state containing previously processed IDs.
    max_cases_per_run : int | None
        Optional cap on number of selected case candidates.

    Returns
    -------
    list[IngestionCandidate]
        Ingestion candidates ordered by case path.
    """
    candidates: list[IngestionCandidate] = []
    processed_ids_by_key = _build_processed_ids_by_key(
        state,
        scan_mode=scan_mode,
        staging_root_basename=staging_root_basename,
    )

    for scan in sorted(scan_results, key=lambda item: item.case_path):
        processed_ids = processed_ids_by_key[
            _case_identity_key(
                scan.case_path,
                scan_mode,
                staging_root_basename=staging_root_basename,
            )
        ]
        new_ids = sorted(set(scan.execution_ids) - processed_ids)

        if not new_ids:
            processed_ids.update(scan.execution_ids)
            continue

        candidates.append(
            IngestionCandidate(
                case_path=scan.case_path,
                execution_ids=scan.execution_ids,
                new_execution_ids=new_ids,
                fingerprint=scan.fingerprint,
            )
        )
        processed_ids.update(scan.execution_ids)

        if max_cases_per_run is not None and len(candidates) >= max_cases_per_run:
            break

    return candidates


# Run Completion and Summaries
# ----------------------------


def _handle_dry_run(
    candidates: list[IngestionCandidate],
    scan_results: list[CaseScanResult],
    submission_qualified_case_count: int,
    discovery_stats: DiscoveryStats,
    *,
    archive_root: Path,
) -> int:
    """Emit dry-run candidate logs and completion summaries.

    Parameters
    ----------
    candidates : list[IngestionCandidate]
        Selected ingestion candidates.
    scan_results : list[CaseScanResult]
        Discovered case scan results.
    submission_qualified_case_count : int
        Count of cases with at least one new execution before per-run limiting.
    discovery_stats : DiscoveryStats
        Archive discovery counters.

    Returns
    -------
    int
        Dry-run exit code (always ``0``).
    """
    logged_candidates = 0
    suppressed_candidates = 0

    for candidate in candidates:
        if logged_candidates < MAX_DRY_RUN_CANDIDATE_LOGS:
            _log_event(
                "dry_run_candidate",
                {
                    "case": _case_log_label(candidate.case_path, archive_root),
                    "execution_count": len(candidate.execution_ids),
                    "new_execution_count": len(candidate.new_execution_ids),
                },
            )
            logged_candidates += 1
        else:
            suppressed_candidates += 1

    if suppressed_candidates:
        _log_event(
            "dry_run_candidate_logs_suppressed",
            {
                "suppressed_count": suppressed_candidates,
                "detail_log_limit": MAX_DRY_RUN_CANDIDATE_LOGS,
            },
        )

    _log_event(
        "dry_run_completed",
        {
            "discovered_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
            "skipped_transient": discovery_stats["skipped_transient"],
            "accepted_execution_ids": discovery_stats["accepted_execution_ids"],
            "rejected_existing_execution_ids": discovery_stats[
                "rejected_existing_execution_ids"
            ],
            "rejected_incomplete_execution_ids": discovery_stats[
                "rejected_incomplete_execution_ids"
            ],
            "rejected_invalid_execution_ids": discovery_stats[
                "rejected_invalid_execution_ids"
            ],
            "transient_execution_ids": discovery_stats["transient_execution_ids"],
            "deferred_execution_ids": discovery_stats["deferred_execution_ids"],
        },
    )
    _log_dry_run_summary(
        discovered_cases=len(scan_results),
        submission_qualified_cases=submission_qualified_case_count,
        selected_submission_cases=len(candidates),
        discovery_stats=discovery_stats,
        candidate_logs_emitted=logged_candidates,
        candidate_logs_suppressed=suppressed_candidates,
    )
    return 0


def _handle_ingest_run(
    candidates: list[IngestionCandidate],
    scan_results: list[CaseScanResult],
    config: IngestorConfig,
    endpoint_url: str,
    state: dict[str, Any],
    submission_qualified_case_count: int,
    discovery_stats: DiscoveryStats,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse],
) -> int:
    """Execute candidate ingestion loop and emit completion summaries.

    Parameters
    ----------
    candidates : list[IngestionCandidate]
        Selected ingestion candidates.
    scan_results : list[CaseScanResult]
        Discovered case scan results.
    config : IngestorConfig
        Runtime configuration values.
    endpoint_url : str
        Fully qualified ingestion endpoint URL.
    state : dict[str, Any]
        Mutable ingestion state payload.
    submission_qualified_case_count : int
        Count of cases with at least one new execution before per-run limiting.
    discovery_stats : DiscoveryStats
        Archive discovery counters.
    sleep_fn : Callable[[float], None]
        Sleep callable used for retry backoff.
    post_request_fn : Callable[..., IngestionRequestResponse]
        HTTP request callable used for ingestion submissions.

    Returns
    -------
    int
        Exit code (``0`` when all candidates succeeded, else ``1``).
    """
    success_count = 0
    failure_count = 0

    for candidate in candidates:
        result = _ingest_case_with_retries(
            candidate,
            endpoint_url,
            config.api_token,
            config.machine_name,
            max_attempts=config.max_attempts,
            timeout_seconds=config.request_timeout_seconds,
            sleep_fn=sleep_fn,
            post_request_fn=post_request_fn,
        )

        if result["ok"]:
            success_count += 1
            body = result["body"] or {}

            _log_event(
                "case_ingested",
                {
                    "case_path": candidate.case_path,
                    "attempts": result["attempts"],
                    "created_count": body.get("created_count"),
                    "duplicate_count": body.get("duplicate_count"),
                    "error_count": len(body.get("errors", []))
                    if isinstance(body.get("errors", []), list)
                    else None,
                },
            )

            _record_successful_case(state, candidate)

            continue

        failure_count += 1
        _log_event(
            "case_ingestion_failed",
            {
                "case_path": candidate.case_path,
                "attempts": result["attempts"],
                "status_code": result["status_code"],
                "error": result["error"],
            },
        )

    _log_event(
        "run_completed",
        {
            "scanned_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            "success_count": success_count,
            "failure_count": failure_count,
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
            "skipped_transient": discovery_stats["skipped_transient"],
            "accepted_execution_ids": discovery_stats["accepted_execution_ids"],
            "rejected_existing_execution_ids": discovery_stats[
                "rejected_existing_execution_ids"
            ],
            "rejected_incomplete_execution_ids": discovery_stats[
                "rejected_incomplete_execution_ids"
            ],
            "rejected_invalid_execution_ids": discovery_stats[
                "rejected_invalid_execution_ids"
            ],
            "transient_execution_ids": discovery_stats["transient_execution_ids"],
            "deferred_execution_ids": discovery_stats["deferred_execution_ids"],
        },
    )
    _log_run_summary(
        scanned_cases=len(scan_results),
        submission_qualified_cases=submission_qualified_case_count,
        selected_submission_cases=len(candidates),
        success_count=success_count,
        failure_count=failure_count,
        discovery_stats=discovery_stats,
    )

    return 1 if failure_count else 0


def _common_summary_fields(discovery_stats: DiscoveryStats) -> dict[str, int]:
    """Build summary fields shared by dry-run and ingest completion logs."""
    return {
        "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
        "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
        "skipped_incomplete": discovery_stats["skipped_incomplete"],
        "skipped_invalid": discovery_stats["skipped_invalid"],
        "skipped_transient": discovery_stats["skipped_transient"],
        "accepted_execution_ids": discovery_stats["accepted_execution_ids"],
        "rejected_existing_execution_ids": discovery_stats[
            "rejected_existing_execution_ids"
        ],
        "rejected_incomplete_execution_ids": discovery_stats[
            "rejected_incomplete_execution_ids"
        ],
        "rejected_invalid_execution_ids": discovery_stats[
            "rejected_invalid_execution_ids"
        ],
        "transient_execution_ids": discovery_stats["transient_execution_ids"],
        "deferred_execution_ids": discovery_stats["deferred_execution_ids"],
    }


def _log_dry_run_summary(
    *,
    discovered_cases: int,
    submission_qualified_cases: int,
    selected_submission_cases: int,
    discovery_stats: DiscoveryStats,
    candidate_logs_emitted: int,
    candidate_logs_suppressed: int,
) -> None:
    """Emit compact dry-run summary event block."""
    summary_fields = _common_summary_fields(discovery_stats)
    _log_event(
        "dry_run_summary_counts",
        {
            "mode": "dry-run",
            "discovered_cases": discovered_cases,
            "submission_qualified_cases": submission_qualified_cases,
            "selected_submission_cases": selected_submission_cases,
            "execution_dirs_scanned": summary_fields["execution_dirs_scanned"],
            "execution_dirs_accepted": summary_fields["execution_dirs_accepted"],
            "skipped_incomplete": summary_fields["skipped_incomplete"],
            "skipped_invalid": summary_fields["skipped_invalid"],
            "skipped_transient": summary_fields["skipped_transient"],
        },
    )
    _log_event(
        "dry_run_summary_candidates",
        {
            "accepted_execution_ids": summary_fields["accepted_execution_ids"],
            "rejected_existing_execution_ids": summary_fields[
                "rejected_existing_execution_ids"
            ],
            "rejected_incomplete_execution_ids": summary_fields[
                "rejected_incomplete_execution_ids"
            ],
            "rejected_invalid_execution_ids": summary_fields[
                "rejected_invalid_execution_ids"
            ],
            "transient_execution_ids": summary_fields["transient_execution_ids"],
            "deferred_execution_ids": summary_fields["deferred_execution_ids"],
            "candidate_logs_emitted": candidate_logs_emitted,
            "candidate_logs_suppressed": candidate_logs_suppressed,
        },
    )


def _log_run_summary(
    *,
    scanned_cases: int,
    submission_qualified_cases: int,
    selected_submission_cases: int,
    success_count: int,
    failure_count: int,
    discovery_stats: DiscoveryStats,
) -> None:
    """Emit compact ingest-run summary event block."""
    summary_fields = _common_summary_fields(discovery_stats)
    _log_event(
        "run_summary_counts",
        {
            "mode": "ingest",
            "scanned_cases": scanned_cases,
            "submission_qualified_cases": submission_qualified_cases,
            "selected_submission_cases": selected_submission_cases,
            "execution_dirs_scanned": summary_fields["execution_dirs_scanned"],
            "execution_dirs_accepted": summary_fields["execution_dirs_accepted"],
            "skipped_incomplete": summary_fields["skipped_incomplete"],
            "skipped_invalid": summary_fields["skipped_invalid"],
            "skipped_transient": summary_fields["skipped_transient"],
        },
    )
    _log_event(
        "run_summary_outcomes",
        {
            "success_count": success_count,
            "failure_count": failure_count,
            "accepted_execution_ids": summary_fields["accepted_execution_ids"],
            "rejected_existing_execution_ids": summary_fields[
                "rejected_existing_execution_ids"
            ],
            "rejected_incomplete_execution_ids": summary_fields[
                "rejected_incomplete_execution_ids"
            ],
            "rejected_invalid_execution_ids": summary_fields[
                "rejected_invalid_execution_ids"
            ],
            "transient_execution_ids": summary_fields["transient_execution_ids"],
            "deferred_execution_ids": summary_fields["deferred_execution_ids"],
        },
    )


# HTTP Requests and Remote State
# ------------------------------


def _persist_discovery_results_with_retries(
    results: list[ExecutionDiscoveryResult],
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> bool:
    """Persist discovery results in bounded batches before any ingestion."""
    deduplicated_results = _deduplicate_discovery_results(results)
    if not deduplicated_results:
        return True
    if post_request_fn is None:
        post_request_fn = _post_discovery_results_request

    for offset in range(0, len(deduplicated_results), DISCOVERY_RESULT_BATCH_SIZE):
        batch = deduplicated_results[offset : offset + DISCOVERY_RESULT_BATCH_SIZE]
        for attempt in range(1, max_attempts + 1):
            try:
                post_request_fn(
                    endpoint_url,
                    api_token,
                    machine_name,
                    results=batch,
                    timeout_seconds=timeout_seconds,
                )
                break
            except IngestionRequestError as exc:
                retrying = exc.transient and attempt < max_attempts
                _log_event(
                    "discovery_results_persistence_failed",
                    {
                        "attempt": attempt,
                        "status_code": exc.status_code,
                        "transient": exc.transient,
                        "retrying": retrying,
                        "error": str(exc),
                    },
                )
                if not retrying:
                    return False
                sleep_fn(2 ** (attempt - 1))

    return True


def _post_discovery_results_request(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    results: list[ExecutionDiscoveryResult],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """POST one JSON discovery-result batch."""
    body = json.dumps(
        {
            "machine_name": machine_name,
            "results": [
                {
                    "case_identity": result.case_identity,
                    "execution_id": result.execution_id,
                    "outcome": result.outcome,
                }
                for result in results
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            parsed_body = json.loads(raw_body) if raw_body else {}
            return {"status_code": response.status, "body": parsed_body}
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


def _ingest_case_with_retries(
    candidate: IngestionCandidate,
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> IngestionAttemptResult:
    """Ingest one case with exponential-backoff retries.

    Parameters
    ----------
    candidate : IngestionCandidate
        Case-level ingestion candidate.
    endpoint_url : str
        Fully qualified ingestion endpoint URL.
    api_token : str
        Bearer token used for API authentication.
    machine_name : str
        Machine label attached to ingested executions.
    max_attempts : int
        Maximum number of attempts for the case request.
    timeout_seconds : int
        HTTP request timeout in seconds.
    sleep_fn : Callable[[float], None]
        Sleep callable used for retry backoff.
    post_request_fn : Callable[..., IngestionRequestResponse] | None, optional
        HTTP request callable. Defaults to internal request function.
    Returns
    -------
    dict[str, Any]
        Structured result containing success flag, attempts, status code,
        response body, and error message.
    """
    if post_request_fn is None:
        post_request_fn = _post_ingestion_request

    for attempt in range(1, max_attempts + 1):
        try:
            response = post_request_fn(
                endpoint_url,
                api_token,
                candidate.case_path,
                machine_name,
                processed_execution_ids=candidate.new_execution_ids,
                timeout_seconds=timeout_seconds,
            )
            body = response.get("body")

            if not isinstance(body, dict):
                body = {}

            return {
                "ok": True,
                "attempts": attempt,
                "status_code": response.get("status_code"),
                "body": body,
                "error": None,
            }
        except IngestionRequestError as exc:
            should_retry = exc.transient and attempt < max_attempts

            _log_event(
                "case_ingestion_request_failed",
                {
                    "case_path": candidate.case_path,
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "transient": exc.transient,
                    "retrying": should_retry,
                    "error": str(exc),
                },
            )

            if should_retry:
                backoff_seconds = 2 ** (attempt - 1)
                sleep_fn(backoff_seconds)
                continue

            return {
                "ok": False,
                "attempts": attempt,
                "status_code": exc.status_code,
                "body": None,
                "error": str(exc),
            }

    return {
        "ok": False,
        "attempts": max_attempts,
        "status_code": None,
        "body": None,
        "error": "Exhausted retries",
    }


def _post_ingestion_request(
    endpoint_url: str,
    api_token: str,
    archive_path: str,
    machine_name: str,
    *,
    processed_execution_ids: list[str],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """Send one path-based ingestion request to SimBoard.

    Parameters
    ----------
    endpoint_url : str
        Fully qualified ingestion endpoint URL.
    api_token : str
        Bearer token used for API authentication.
    archive_path : str
        Case directory path under the mounted archive.
    machine_name : str
        Machine label attached to ingested executions.
    timeout_seconds : int
        HTTP request timeout in seconds.

    Returns
    -------
    dict[str, Any]
        Response payload containing ``status_code`` and parsed ``body``.

    Raises
    ------
    IngestionRequestError
        Raised on HTTP/network timeout failures with retry metadata.
    """
    payload = {
        "archive_path": archive_path,
        "machine_name": machine_name,
        "processed_execution_ids": processed_execution_ids,
    }
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
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
            f"URL error: {exc.reason}", status_code=None, transient=True
        ) from exc
    except TimeoutError as exc:
        raise IngestionRequestError(
            "Request timed out", status_code=None, transient=True
        ) from exc


def _fetch_ingestion_state(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Fetch database-backed ingestion state from SimBoard API."""
    query = urllib.parse.urlencode({"machine_name": machine_name})
    request = urllib.request.Request(
        f"{endpoint_url}?{query}",
        headers={"Authorization": f"Bearer {api_token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            try:
                parsed_body = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError as exc:
                raise IngestionRequestError(
                    f"Invalid JSON response: {exc}",
                    status_code=response.status,
                    transient=False,
                ) from exc

            return _normalize_remote_state(parsed_body)
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except urllib.error.URLError as exc:
        raise IngestionRequestError(
            f"URL error: {exc.reason}", status_code=None, transient=True
        ) from exc
    except TimeoutError as exc:
        raise IngestionRequestError(
            "Request timed out", status_code=None, transient=True
        ) from exc


def _fetch_archive_checkpoints(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    archive_name: str,
    *,
    archive_start: str | None,
    archive_end: str | None,
    timeout_seconds: int,
) -> set[str]:
    """Fetch completed immutable snapshot keys from SimBoard."""
    query_values = {"machine_name": machine_name, "archive_name": archive_name}
    if archive_start is not None:
        query_values["archive_start"] = archive_start
    if archive_end is not None:
        query_values["archive_end"] = archive_end
    request = urllib.request.Request(
        f"{endpoint_url}?{urllib.parse.urlencode(query_values)}",
        headers={"Authorization": f"Bearer {api_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            body = json.loads(raw_body) if raw_body else {}
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IngestionRequestError(
            f"Checkpoint request failed: {exc}",
            status_code=None,
            transient=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise IngestionRequestError(
            f"Invalid checkpoint response: {exc}",
            status_code=None,
            transient=False,
        ) from exc

    if not isinstance(body, dict) or not isinstance(body.get("snapshots"), list):
        raise IngestionRequestError(
            "Invalid checkpoint response payload.",
            status_code=None,
            transient=False,
        )
    snapshots = body["snapshots"]
    return {
        f"{snapshot['archive_month']}/{snapshot['snapshot_name']}"
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        and isinstance(snapshot.get("archive_month"), str)
        and isinstance(snapshot.get("snapshot_name"), str)
    }


def _persist_archive_checkpoints_with_retries(
    snapshot_keys: set[str],
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    archive_name: str,
    *,
    max_attempts: int,
    timeout_seconds: int,
    sleep_fn: Callable[[float], None],
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
) -> bool:
    """Persist settled immutable snapshot keys with bounded retries."""
    if not snapshot_keys:
        return True
    if post_request_fn is None:
        post_request_fn = _post_archive_checkpoints_request
    for attempt in range(1, max_attempts + 1):
        try:
            post_request_fn(
                endpoint_url,
                api_token,
                machine_name,
                archive_name=archive_name,
                snapshot_keys=sorted(snapshot_keys),
                timeout_seconds=timeout_seconds,
            )
            return True
        except IngestionRequestError as exc:
            retrying = exc.transient and attempt < max_attempts
            _log_event(
                "archive_checkpoint_persistence_failed",
                {
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "retrying": retrying,
                    "error": str(exc),
                },
            )
            if not retrying:
                return False
            sleep_fn(2 ** (attempt - 1))
    return False


def _post_archive_checkpoints_request(
    endpoint_url: str,
    api_token: str,
    machine_name: str,
    *,
    archive_name: str,
    snapshot_keys: list[str],
    timeout_seconds: int,
) -> IngestionRequestResponse:
    """POST one completed archive-checkpoint batch."""
    body = json.dumps(
        {
            "machine_name": machine_name,
            "archive_name": archive_name,
            "snapshots": [
                {
                    "archive_month": key.split("/", 1)[0],
                    "snapshot_name": key.split("/", 1)[1],
                }
                for key in snapshot_keys
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint_url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            return {
                "status_code": response.status,
                "body": json.loads(raw_body) if raw_body else {},
            }
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        raise IngestionRequestError(
            f"HTTP {exc.code}: {response_text}",
            status_code=exc.code,
            transient=_is_transient_status(exc.code),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IngestionRequestError(
            f"Checkpoint request failed: {exc}",
            status_code=None,
            transient=True,
        ) from exc


def _normalize_remote_state(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize API state response into runner-compatible structure."""
    if not isinstance(body, dict):
        raise IngestionRequestError(
            "Invalid ingestion state response payload.",
            status_code=None,
            transient=False,
        )

    raw_cases = body.get("cases", {})
    if not isinstance(raw_cases, dict):
        raw_cases = {}

    cases: dict[str, dict[str, Any]] = {}
    for case_path, case_state in raw_cases.items():
        if not isinstance(case_path, str) or not isinstance(case_state, dict):
            continue

        processed_execution_ids = sorted(_case_state_processed_ids(case_state))
        fingerprint = case_state.get("fingerprint")
        if not isinstance(fingerprint, str):
            fingerprint = _compute_case_fingerprint(processed_execution_ids)

        cases[case_path] = {
            "processed_execution_ids": processed_execution_ids,
            "fingerprint": fingerprint,
        }

    raw_discovery_results = body.get("discovery_results", {})
    discovery_results: dict[str, list[dict[str, str]]] = {}
    if isinstance(raw_discovery_results, dict):
        for case_identity, raw_results in raw_discovery_results.items():
            if not isinstance(case_identity, str) or not isinstance(raw_results, list):
                continue
            normalized_results = [
                {
                    "case_identity": case_identity,
                    "execution_id": result["execution_id"],
                    "outcome": result["outcome"],
                }
                for result in raw_results
                if isinstance(result, dict)
                and isinstance(result.get("execution_id"), str)
                and result.get("outcome")
                in {"accepted", "rejected_incomplete", "rejected_invalid"}
            ]
            if normalized_results:
                discovery_results[case_identity] = normalized_results

    return {
        "version": STATE_VERSION,
        "cases": cases,
        "discovery_results": discovery_results,
        "updated_at": _utc_now_iso(),
    }


# State, Fingerprints, and Shared Helpers
# ---------------------------------------


def _new_discovery_stats() -> DiscoveryStats:
    """Return an initialized discovery stats dictionary."""
    return {
        "execution_dirs_scanned": 0,
        "execution_dirs_accepted": 0,
        "skipped_incomplete": 0,
        "skipped_invalid": 0,
        "skipped_transient": 0,
        "accepted_execution_ids": 0,
        "rejected_existing_execution_ids": 0,
        "rejected_incomplete_execution_ids": 0,
        "rejected_invalid_execution_ids": 0,
        "transient_execution_ids": 0,
        "deferred_execution_ids": 0,
    }


def _normalized_api_base_url(api_base_url: str) -> str:
    """Normalize a SimBoard base URL to include ``API_BASE``.

    Parameters
    ----------
    api_base_url : str
        Raw API base URL from configuration.

    Returns
    -------
    str
        URL without trailing slash and with ``API_BASE`` suffix.
    """
    stripped = api_base_url.rstrip("/")
    if stripped.endswith(API_BASE):
        return stripped

    return f"{stripped}{API_BASE}"


if __name__ == "__main__":
    raise SystemExit(main())
