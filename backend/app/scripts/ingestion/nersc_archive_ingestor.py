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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.api.version import API_BASE
from app.features.ingestion.parsers.parser import _locate_metadata_files
from app.scripts.ingestion.archive_discovery import (
    _scan_archive,
    _settled_archive_snapshot_keys,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_RESULT_BATCH_SIZE,
    MAX_DRY_RUN_CANDIDATE_LOGS,
    STATE_VERSION,
    CaseScanResult,
    DiscoveryStats,
    ExecutionDiscoveryResult,
    IngestionAttemptResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    UnsupportedArchiveLayoutError,
    _build_config_from_env,
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
