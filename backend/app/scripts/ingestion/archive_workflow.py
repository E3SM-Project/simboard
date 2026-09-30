"""Shared run workflow helpers for archive ingestion runners."""

from __future__ import annotations

import sys
import tarfile
from contextlib import AbstractContextManager, nullcontext
from typing import Any, Callable

from tqdm import tqdm

from app.scripts.ingestion.archive_client import (
    _ingest_case_with_retries,
    _persist_archive_checkpoints_with_retries,
    _persist_discovery_results_with_retries,
)
from app.scripts.ingestion.archive_discovery import _settled_archive_snapshot_keys
from app.scripts.ingestion.archive_ingestor_core import (
    ArchiveCheckpointPersistenceCallback,
    ArchiveSnapshotScan,
    CaseSubmissionCallback,
    DiscoveryResultsPersistenceCallback,
    DiscoveryStats,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestorConfig,
    IngestorRunReport,
    SleepCallback,
    StructuredLogCallback,
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
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Log sanitized runtime configuration for one ingestor run."""
    log_event_fn = log_event_fn or _log_event
    log_event_fn(
        "startup_configuration_api",
        {
            "api_base_url": config.api_base_url,
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


def _log_scan_completed(
    candidates: list[IngestionCandidate],
    submission_qualified_case_count: int,
    discovery_stats: DiscoveryStats,
    *,
    log_event_fn: StructuredLogCallback | None = None,
) -> None:
    """Record selection and emit validation/cache diagnostics once."""
    log_event_fn = log_event_fn or _log_event
    log_event_fn(
        "scan_completed",
        {
            "submission_qualified_cases": submission_qualified_case_count,
            "selected_submission_cases": len(candidates),
            **{
                key: discovery_stats[key]
                for key in (
                    "execution_dirs_scanned",
                    "execution_dirs_accepted",
                    "skipped_incomplete",
                    "skipped_invalid",
                    "skipped_transient",
                )
            },
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


def _handle_ingest_run(
    candidates: list[IngestionCandidate],
    config: IngestorConfig,
    endpoint_url: str,
    state: dict[str, Any],
    sleep_fn: SleepCallback,
    post_request_fn: CaseSubmissionCallback,
    *,
    log_event_fn: StructuredLogCallback | None = None,
    candidate_preparer: (
        Callable[[IngestionCandidate], AbstractContextManager[CaseSubmissionCallback]]
        | None
    ) = None,
    run_report: IngestorRunReport | None = None,
) -> int:
    """Submit selected cases and record their final outcomes."""
    log_event_fn = log_event_fn or _log_event
    success_count = 0
    failure_count = 0

    for candidate in tqdm(
        candidates, desc="Ingesting cases", unit="case", disable=not sys.stderr.isatty()
    ):
        try:
            submission = (
                nullcontext(post_request_fn)
                if candidate_preparer is None
                else candidate_preparer(candidate)
            )
            with submission as submit_case:
                result = _ingest_case_with_retries(
                    candidate,
                    endpoint_url,
                    config.api_token,
                    config.machine_name,
                    max_attempts=config.max_attempts,
                    timeout_seconds=config.request_timeout_seconds,
                    sleep_fn=sleep_fn,
                    post_request_fn=submit_case,
                )
        except (IngestionRequestError, OSError, tarfile.TarError) as exc:
            result = {
                "ok": False,
                "attempts": 0,
                "status_code": (
                    exc.status_code if isinstance(exc, IngestionRequestError) else None
                ),
                "body": None,
                "error": str(exc),
            }

        if result["ok"]:
            success_count += 1
            body = result["body"]
            if not isinstance(body, dict):
                body = {}
            log_event_fn(
                "case_submission_details",
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
            log_event_fn("case_ingested", {"case_path": candidate.case_path})
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

    # Observed before suppression; completion is independent of success.
    log_event_fn("run_completed", None)

    if run_report is not None:
        run_report.ingestion_success_count = success_count
        run_report.ingestion_failure_count = failure_count

    return 1 if failure_count else 0
