"""Shared run workflow helpers for archive ingestion runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.scripts.ingestion.archive_client import (
    _ingest_case_with_retries,
    _persist_archive_checkpoints_with_retries,
    _persist_discovery_results_with_retries,
)
from app.scripts.ingestion.archive_discovery import _settled_archive_snapshot_keys
from app.scripts.ingestion.archive_ingestor_core import (
    MAX_DRY_RUN_CANDIDATE_LOGS,
    ArchiveCheckpointPersistenceCallback,
    ArchiveSnapshotScan,
    CaseScanResult,
    CaseSubmissionCallback,
    DiscoveryResultsPersistenceCallback,
    DiscoveryStats,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestorConfig,
    SleepCallback,
    StructuredLogCallback,
    _case_log_label,
    _log_event,
    _record_successful_case,
)


def _validate_run_preconditions(
    config: IngestorConfig,
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> bool:
    """Validate filesystem and authentication requirements for one run."""
    log_event_fn = log_event_fn or _log_event
    if not config.archive_root.is_dir():
        log_event_fn(
            "archive_root_missing",
            {"archive_root": str(config.archive_root)},
        )
        return False

    if (not config.dry_run or config.dry_run_use_remote_state) and not config.api_token:
        log_event_fn(
            "configuration_error",
            {"error": "SIMBOARD_API_TOKEN is required"},
        )
        return False

    return True


def _log_startup_configuration(
    config: IngestorConfig,
    endpoint_url: str,
    state_endpoint_url: str,
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Log sanitized runtime configuration for one ingestor run."""
    log_event_fn = log_event_fn or _log_event
    log_event_fn("startup_configuration_begin", None)
    log_event_fn(
        "startup_configuration_api",
        {
            "api_base_url": config.api_base_url,
            "endpoint_url": endpoint_url,
            "state_endpoint_url": state_endpoint_url,
        },
    )
    log_event_fn(
        "startup_configuration_paths",
        {
            "scan_mode": config.scan_mode,
            "archive_root": str(config.archive_root),
            "archive_year_start": config.archive_year_start,
            "archive_year_end": config.archive_year_end,
        },
    )
    log_event_fn(
        "startup_configuration_runtime",
        {
            "machine_name": config.machine_name,
            "dry_run": config.dry_run,
            "dry_run_use_remote_state": config.dry_run_use_remote_state,
            "max_cases_per_run": config.max_cases_per_run,
            "max_attempts": config.max_attempts,
            "request_timeout_seconds": config.request_timeout_seconds,
        },
    )
    log_event_fn(
        "startup_configuration_auth",
        {"has_api_token": bool(config.api_token)},
    )
    log_event_fn("startup_configuration_end", None)


def _log_scan_completed(
    config: IngestorConfig,
    scan_results: list[CaseScanResult],
    candidates: list[IngestionCandidate],
    submission_qualified_case_count: int,
    discovery_stats: DiscoveryStats,
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Log stable discovery fields after a successful archive scan."""
    log_event_fn = log_event_fn or _log_event
    log_event_fn(
        "scan_completed",
        {
            "scan_mode": config.scan_mode,
            "archive_root": str(config.archive_root),
            "discovered_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            **_common_summary_fields(discovery_stats),
        },
    )


def _persist_discovery_results(
    discovery_results: list[ExecutionDiscoveryResult],
    endpoint_url: str,
    config: IngestorConfig,
    sleep_fn: SleepCallback,
    post_request_fn: DiscoveryResultsPersistenceCallback | None,
) -> bool:
    """Persist discovery outcomes before candidate ingestion begins."""
    return _persist_discovery_results_with_retries(
        discovery_results,
        endpoint_url,
        config.api_token,
        config.machine_name,
        max_attempts=config.max_attempts,
        timeout_seconds=config.request_timeout_seconds,
        sleep_fn=sleep_fn,
        post_request_fn=post_request_fn,
    )


def _finalize_archive_checkpoints(
    snapshot_scan: ArchiveSnapshotScan,
    state: dict[str, Any],
    discovery_results: list[ExecutionDiscoveryResult],
    endpoint_url: str,
    config: IngestorConfig,
    sleep_fn: SleepCallback,
    post_request_fn: ArchiveCheckpointPersistenceCallback | None,
) -> bool:
    """Settle and persist archive checkpoints after candidate ingestion."""
    if config.scan_mode != "archive":
        return True

    settled_snapshot_keys = _settled_archive_snapshot_keys(
        snapshot_scan,
        state,
        discovery_results,
    )
    return _persist_archive_checkpoints_with_retries(
        settled_snapshot_keys,
        endpoint_url,
        config.api_token,
        config.machine_name,
        snapshot_scan.archive_name,
        max_attempts=config.max_attempts,
        timeout_seconds=config.request_timeout_seconds,
        sleep_fn=sleep_fn,
        post_request_fn=post_request_fn,
    )


def _handle_dry_run(
    candidates: list[IngestionCandidate],
    scan_results: list[CaseScanResult],
    submission_qualified_case_count: int,
    discovery_stats: DiscoveryStats,
    *,
    archive_root: Path,
    log_event_fn: StructuredLogCallback | None = None,
) -> int:
    """Emit dry-run candidate logs and completion summaries."""
    log_event_fn = log_event_fn or _log_event
    logged_candidates = 0
    suppressed_candidates = 0

    for candidate in candidates:
        if logged_candidates < MAX_DRY_RUN_CANDIDATE_LOGS:
            log_event_fn(
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
        log_event_fn(
            "dry_run_candidate_logs_suppressed",
            {
                "suppressed_count": suppressed_candidates,
                "detail_log_limit": MAX_DRY_RUN_CANDIDATE_LOGS,
            },
        )

    log_event_fn(
        "dry_run_completed",
        {
            "discovered_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            **_common_summary_fields(discovery_stats),
        },
    )
    _log_dry_run_summary(
        discovered_cases=len(scan_results),
        submission_qualified_cases=submission_qualified_case_count,
        selected_submission_cases=len(candidates),
        discovery_stats=discovery_stats,
        candidate_logs_emitted=logged_candidates,
        candidate_logs_suppressed=suppressed_candidates,
        log_event_fn=log_event_fn,
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
    sleep_fn: SleepCallback,
    post_request_fn: CaseSubmissionCallback,
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> int:
    """Execute candidate ingestion loop and emit completion summaries."""
    log_event_fn = log_event_fn or _log_event
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
            log_event_fn(
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
        log_event_fn(
            "case_ingestion_failed",
            {
                "case_path": candidate.case_path,
                "attempts": result["attempts"],
                "status_code": result["status_code"],
                "error": result["error"],
            },
        )

    log_event_fn(
        "run_completed",
        {
            "scanned_cases": len(scan_results),
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            "success_count": success_count,
            "failure_count": failure_count,
            **_common_summary_fields(discovery_stats),
        },
    )
    _log_run_summary(
        scanned_cases=len(scan_results),
        submission_qualified_cases=submission_qualified_case_count,
        selected_submission_cases=len(candidates),
        success_count=success_count,
        failure_count=failure_count,
        discovery_stats=discovery_stats,
        log_event_fn=log_event_fn,
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
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Emit compact dry-run summary event block."""
    log_event_fn = log_event_fn or _log_event
    summary_fields = _common_summary_fields(discovery_stats)
    log_event_fn(
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
    log_event_fn(
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
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Emit compact ingest-run summary event block."""
    log_event_fn = log_event_fn or _log_event
    summary_fields = _common_summary_fields(discovery_stats)
    log_event_fn(
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
    log_event_fn(
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
