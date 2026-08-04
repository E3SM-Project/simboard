"""Discover and select execution candidates from archive filesystems."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any, Callable

from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
    _locate_metadata_files,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DEFAULT_PERF_ARCHIVE_ROOT,
    DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES,
    ArchiveSnapshotScan,
    CaseCollectionLogData,
    CaseScanResult,
    DiscoveryStats,
    ExecutionCollectionDecision,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestorConfig,
    MetadataLocator,
    _build_discovery_results_by_key,
    _case_log_label,
    _case_state_processed_ids,
    _compute_case_fingerprint,
    _deduplicate_discovery_results,
    _log_event,
)
from app.scripts.ingestion.archive_layout import (
    _build_case_path_filter,
    _build_walk_dir_filter,
    _case_identity_key,
    _enumerate_archive_snapshot_keys,
    _record_archive_snapshot_reference,
)

EXECUTION_DIR_PATTERN = re.compile(r"\d+\.\d+-\d+$")


def _scan_archive(
    config: IngestorConfig,
    state: dict[str, Any],
    metadata_locator: MetadataLocator,
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
            partial(
                _handle_archive_walk_error,
                config=config,
                snapshot_scan=snapshot_scan,
            )
            if config.scan_mode == "archive"
            else None
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


def _handle_archive_walk_error(
    exc: OSError,
    *,
    config: IngestorConfig,
    snapshot_scan: ArchiveSnapshotScan,
) -> None:
    """Mark an archive traversal incomplete and log its walk error."""
    snapshot_scan.traversal_complete = False
    _log_event(
        "archive_scan_failed",
        {
            "scan_mode": config.scan_mode,
            "archive_root": str(config.archive_root),
            "error": f"{exc.__class__.__name__}: {exc}",
        },
    )


def _discover_case_executions(
    archive_root: Path,
    metadata_locator: MetadataLocator = _locate_metadata_files,
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
    metadata_locator: MetadataLocator,
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
    metadata_locator: MetadataLocator,
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


# Discovery Results and Candidate Selection
# -----------------------------------------


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

    for scan in sorted(scan_results, key=_case_scan_result_sort_key):
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


def _case_scan_result_sort_key(scan_result: CaseScanResult) -> str:
    """Return deterministic case-path ordering key for scan results."""
    return scan_result.case_path


# Discovery Statistics
# --------------------


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
