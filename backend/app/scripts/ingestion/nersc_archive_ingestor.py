"""Scan NERSC archives and trigger SimBoard path-based ingestion.

This script is intended for scheduled execution (for example, a CronJob)
against a bind-mounted performance archive. Runtime configuration is read
from environment variables (for example ``SIMBOARD_API_BASE_URL``,
``SIMBOARD_API_TOKEN``, ``PERF_ARCHIVE_ROOT``, and ``DRY_RUN``).

Each run executes four phases:

  1. Discover and collect parseable execution directories grouped by case path.
  2. Fetch persisted per-case state from SimBoard API.
  3. Submit one ingestion request per changed case with retry/backoff.
  4. Rely on DB writes from successful ingestions for future idempotent runs.

Runner terms used heavily in this module and its logs:

    - submission-qualified case / ``submission_qualified_cases``:
        case count with at least one newly discovered complete execution ID before
        applying any ``MAX_CASES_PER_RUN`` cap
    - selected submission case / ``selected_submission_cases``:
        submission-qualified case count selected for the current run after applying
        any ``MAX_CASES_PER_RUN`` cap
    - ``execution_dirs_scanned``:
        execution directory count whose names matched the execution pattern and
        were sent through discovery validation
    - ``execution_dirs_accepted``:
        scanned execution directory count that passed validation and were retained
        as valid discovered executions
    - ``skipped_incomplete``:
        execution directory count rejected during discovery because required
        metadata files or fields were missing or incomplete
    - ``skipped_invalid``:
        execution directory count rejected during discovery because metadata was
        invalid or the directory could not be read
    - ``accepted_execution_ids``:
        newly discovered valid execution ID count selected for the current run
    - ``rejected_existing_execution_ids``:
        valid discovered execution ID count already present in stored processed
        state
    - ``rejected_incomplete_execution_ids``:
        execution ID count rejected during discovery as incomplete because required
        metadata files or fields were missing or incomplete
    - ``rejected_invalid_execution_ids``:
        execution ID count rejected during discovery as invalid or unreadable
        because metadata was invalid or the directory could not be read
    - deferred execution / ``deferred_execution_ids``:
        newly discovered valid execution ID count not selected for the current run
        because per-run case capping stopped earlier selection
    - ``processed_execution_ids``:
        execution ID count already recorded in stored processed state for one case

Canonical definitions live in ``docs/architecture/metadata-ingestion.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from app.api.version import API_BASE
from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
    _locate_metadata_files,
)

logger = _setup_custom_logger(__name__)
logger.setLevel(logging.INFO)

# The execution directory name pattern (example: 55387330.260706-012656)
EXECUTION_DIR_PATTERN = re.compile(r"\d+\.\d+-\d+$")
# Transient HTTP status codes that may be retried with backoff.
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
# The state version number used to detect incompatible state changes. Increment
# this number whenever the state format changes in a way that is not backward
# compatible.
STATE_VERSION = 1
# Default base URL for SimBoard API when SIMBOARD_API_BASE_URL is not set.
# This is the internal service name used in the NERSC Spin Kubernetes cluster
# for the backend service.
DEFAULT_API_BASE_URL = "http://backend:8000"
# Default root path of the mounted performance archive when PERF_ARCHIVE_ROOT is not set.
DEFAULT_ARCHIVE_ROOT = "/performance_archive"
# Default machine name used for state persistence when MACHINE_NAME is not set.
DEFAULT_MACHINE_NAME = "perlmutter"
# Default maximum number of attempts for each ingestion request.
DEFAULT_MAX_ATTEMPTS = 3
# Default timeout in seconds for each ingestion request. This is a conservative
# value that should be sufficient for most ingestion requests, but can be
# overridden by the REQUEST_TIMEOUT_SECONDS environment variable.
DEFAULT_TIMEOUT_SECONDS = 60
# In dry-run mode, limit the number of candidate logs emitted to avoid excessive
# log volume.
MAX_DRY_RUN_CANDIDATE_LOGS = 20
# Log archive scan progress every N directories visited to avoid excessive log
# volume.
DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES = 250
# The order for event fields in structured logs. This is used to ensure
# consistent field ordering in structured logs for easier parsing and analysis.
EVENT_FIELD_ORDER: dict[str, tuple[str, ...]] = {
    "run_started": ("mode", "archive_root"),
    "run_finished": ("mode", "exit_code", "duration_seconds"),
    "archive_scan_started": ("archive_root",),
    "archive_scan_progress": (
        "archive_root",
        "directories_visited",
        "discovered_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "duration_seconds",
    ),
    "archive_scan_completed": (
        "archive_root",
        "directories_visited",
        "discovered_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "duration_seconds",
    ),
    "case_collection_begin": (
        "case",
        "execution_count_total",
        "execution_count_valid",
        "execution_count_existing",
        "execution_count_new",
        "execution_count_selected_new",
        "execution_count_deferred",
        "execution_count_rejected_incomplete",
        "execution_count_rejected_invalid",
    ),
    "execution_collection_decision": (
        "case",
        "execution_id",
        "decision",
        "reason",
        "error_codes",
        "error_count",
        "missing_file_specs",
        "detail",
    ),
    "case_collection_summary": (
        "case",
        "accepted",
        "rejected_existing",
        "rejected_incomplete",
        "rejected_invalid",
        "deferred",
    ),
    "scan_completed": (
        "archive_root",
        "discovered_cases",
        "submission_qualified_cases",
        "selected_submission_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_incomplete",
        "skipped_invalid",
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "deferred_execution_ids",
    ),
    "dry_run_candidate": ("case", "execution_count", "new_execution_count"),
    "startup_configuration_api": (
        "api_base_url",
        "endpoint_url",
        "state_endpoint_url",
    ),
    "startup_configuration_paths": ("archive_root",),
    "startup_configuration_runtime": (
        "machine_name",
        "dry_run",
        "max_cases_per_run",
        "max_attempts",
        "request_timeout_seconds",
    ),
    "startup_configuration_auth": ("has_api_token",),
    "dry_run_summary_counts": (
        "mode",
        "discovered_cases",
        "submission_qualified_cases",
        "selected_submission_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_incomplete",
        "skipped_invalid",
    ),
    "dry_run_summary_candidates": (
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "deferred_execution_ids",
        "candidate_logs_emitted",
        "candidate_logs_suppressed",
    ),
    "run_summary_counts": (
        "mode",
        "scanned_cases",
        "submission_qualified_cases",
        "selected_submission_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_incomplete",
        "skipped_invalid",
    ),
    "run_summary_outcomes": (
        "success_count",
        "failure_count",
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "deferred_execution_ids",
    ),
    "case_ingested": (
        "case_path",
        "attempts",
        "created_count",
        "duplicate_count",
        "error_count",
    ),
    "case_ingestion_failed": ("case_path", "attempts", "status_code", "error"),
}


@dataclass(frozen=True)
class CaseScanResult:
    """Discovered execution IDs for one case directory."""

    case_path: str
    execution_ids: list[str]
    fingerprint: str


@dataclass(frozen=True)
class IngestionCandidate:
    """One case-level ingestion call candidate."""

    case_path: str
    execution_ids: list[str]
    new_execution_ids: list[str]
    fingerprint: str


@dataclass(frozen=True)
class IngestorConfig:
    """Runtime configuration for the ingestion runner."""

    # API endpoint and token for ingestion requests.
    api_base_url: str
    #  Bearer token for SimBoard API authentication.
    api_token: str
    # Absolute path to the mounted performance archive root.
    archive_root: Path
    # Name of the machine being scanned (used for state persistence).
    machine_name: str
    # Whether to perform a dry-run scan without ingestion requests.
    dry_run: bool
    # Optional cap on the number of cases to submit per run.
    max_cases_per_run: int | None
    # Maximum number of attempts for each ingestion request.
    max_attempts: int
    # Timeout in seconds for each ingestion request.
    request_timeout_seconds: int


class IngestionRequestError(Exception):
    """Error raised for API requests, with retry metadata."""

    def __init__(
        self,
        message: str,
        status_code: int | None,
        transient: bool,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.transient = transient


class DiscoveryStats(TypedDict):
    """Discovery counters captured during archive scanning."""

    execution_dirs_scanned: int
    execution_dirs_accepted: int
    skipped_incomplete: int
    skipped_invalid: int
    accepted_execution_ids: int
    rejected_existing_execution_ids: int
    rejected_incomplete_execution_ids: int
    rejected_invalid_execution_ids: int
    deferred_execution_ids: int


class IngestionRequestResponse(TypedDict):
    """HTTP response payload returned by one ingestion request."""

    status_code: int
    body: dict[str, Any]


class IngestionAttemptResult(TypedDict):
    """Result payload for one candidate ingestion attempt sequence."""

    ok: bool
    attempts: int
    status_code: int | None
    body: dict[str, Any] | None
    error: str | None


@dataclass(frozen=True)
class ExecutionCollectionDecision:
    """Structured log decision for one discovered execution directory."""

    case_path: str
    execution_id: str
    decision: str
    reason: str
    error_count: int | None = None
    error_codes: list[str] | None = None
    missing_file_specs: list[str] | None = None
    detail: str | None = None

    def to_log_fields(self, case: str | None = None) -> dict[str, Any]:
        """Render log fields for one execution decision."""
        fields: dict[str, Any] = {
            "case": self.case_path if case is None else case,
            "execution_id": self.execution_id,
            "decision": self.decision,
            "reason": self.reason,
        }
        if self.error_count is not None:
            fields["error_count"] = self.error_count
        if self.error_codes:
            fields["error_codes"] = self.error_codes
        if self.missing_file_specs:
            fields["missing_file_specs"] = self.missing_file_specs
        if self.detail is not None:
            fields["detail"] = self.detail

        return fields


@dataclass
class CaseCollectionLogData:
    """Discovery and decision inputs needed to log one case block."""

    case_path: str
    execution_count_total: int = 0
    valid_execution_ids: set[str] = field(default_factory=set)
    rejected_decisions: list[ExecutionCollectionDecision] = field(default_factory=list)


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


def _build_config_from_env() -> IngestorConfig:
    """Build and validate runtime config from environment variables.

    Returns
    -------
    IngestorConfig
        Validated ingestion runner configuration.

    Raises
    ------
    ValueError
        Raised when numeric options are invalid.
    """
    api_base_url = os.getenv("SIMBOARD_API_BASE_URL", DEFAULT_API_BASE_URL)
    api_token = os.getenv("SIMBOARD_API_TOKEN", "")
    archive_root = Path(os.getenv("PERF_ARCHIVE_ROOT", DEFAULT_ARCHIVE_ROOT)).resolve()
    machine_name = os.getenv("MACHINE_NAME", DEFAULT_MACHINE_NAME)
    dry_run = _parse_bool(os.getenv("DRY_RUN"), default=False)
    max_cases_per_run = _parse_optional_int(os.getenv("MAX_CASES_PER_RUN"))
    if max_cases_per_run is not None and max_cases_per_run <= 0:
        raise ValueError("MAX_CASES_PER_RUN must be greater than 0 when provided")

    max_attempts = int(os.getenv("MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS)))
    if max_attempts <= 0:
        raise ValueError("MAX_ATTEMPTS must be greater than 0")

    timeout_seconds = int(
        os.getenv("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    )
    if timeout_seconds <= 0:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be greater than 0")

    return IngestorConfig(
        api_base_url=api_base_url,
        api_token=api_token,
        archive_root=archive_root,
        machine_name=machine_name,
        dry_run=dry_run,
        max_cases_per_run=max_cases_per_run,
        max_attempts=max_attempts,
        request_timeout_seconds=timeout_seconds,
    )


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a nullable environment-style boolean string.

    Parameters
    ----------
    value : str | None
        Raw string value from args or environment.
    default : bool, optional
        Fallback value when parsing fails.

    Returns
    -------
    bool
        Parsed boolean or default.
    """
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


def _parse_optional_int(value: str | None) -> int | None:
    """Parse an optional integer string.

    Parameters
    ----------
    value : str | None
        Raw value that may be empty or null.

    Returns
    -------
    int | None
        Parsed integer when present, otherwise ``None``.
    """
    if value is None or value.strip() == "":
        return None

    parsed = int(value)
    return parsed


def _run_ingestor(
    config: IngestorConfig,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    sleep_fn: Callable[[float], None] = time.sleep,
    post_request_fn: Callable[..., IngestionRequestResponse] | None = None,
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

    (scan_results, candidates, submission_qualified_case_count, discovery_stats) = (
        _scan_archive(config, state, metadata_locator=metadata_locator)
    )

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


def _scan_archive(
    config: IngestorConfig,
    state: dict[str, Any],
    metadata_locator: Callable[[str], object],
) -> tuple[
    list[CaseScanResult],
    list[IngestionCandidate],
    int,
    DiscoveryStats,
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
    grouped_executions = _discover_case_executions(
        config.archive_root, metadata_locator, discovery_stats, case_collection_data
    )
    scan_results = _build_case_scan_results(grouped_executions)
    all_candidates = _build_ingestion_candidates(
        scan_results, state, max_cases_per_run=None
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
    )

    return (
        scan_results,
        candidates,
        len(all_candidates),
        discovery_stats,
    )


def _discover_case_executions(
    archive_root: Path,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    stats: DiscoveryStats | None = None,
    case_collection_data: dict[str, CaseCollectionLogData] | None = None,
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

    _log_event("archive_scan_started", {"archive_root": archive_root_str})

    for dirpath, dirnames, _ in os.walk(archive_root):
        directories_visited += 1
        case_dir = Path(dirpath)
        for dirname in dirnames:
            if not EXECUTION_DIR_PATTERN.fullmatch(dirname):
                continue

            _collect_case_execution(
                grouped,
                case_dir,
                dirname,
                metadata_locator=metadata_locator,
                stats=effective_stats,
                case_collection_data=case_collection_data,
            )

        if directories_visited % DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES == 0:
            _log_archive_scan_progress(
                event="archive_scan_progress",
                archive_root=archive_root_str,
                directories_visited=directories_visited,
                grouped=grouped,
                stats=effective_stats,
                started_at=scan_started_at,
            )

    _log_archive_scan_progress(
        event="archive_scan_completed",
        archive_root=archive_root_str,
        directories_visited=directories_visited,
        grouped=grouped,
        stats=effective_stats,
        started_at=scan_started_at,
    )

    return {case_path: sorted(exec_ids) for case_path, exec_ids in grouped.items()}


def _log_archive_scan_progress(
    *,
    event: str,
    archive_root: str,
    directories_visited: int,
    grouped: dict[str, set[str]],
    stats: DiscoveryStats | None,
    started_at: float,
) -> None:
    """Emit a structured archive-scan progress or completion log."""
    _log_event(
        event,
        {
            "archive_root": archive_root,
            "directories_visited": directories_visited,
            "discovered_cases": len(grouped),
            "execution_dirs_scanned": (
                0 if stats is None else stats["execution_dirs_scanned"]
            ),
            "execution_dirs_accepted": (
                0 if stats is None else stats["execution_dirs_accepted"]
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
    stats.setdefault("accepted_execution_ids", 0)
    stats.setdefault("rejected_existing_execution_ids", 0)
    stats.setdefault("rejected_incomplete_execution_ids", 0)
    stats.setdefault("rejected_invalid_execution_ids", 0)
    stats.setdefault("deferred_execution_ids", 0)


def _collect_case_execution(
    grouped: dict[str, set[str]],
    case_dir: Path,
    execution_id: str,
    *,
    metadata_locator: Callable[[str], object],
    stats: DiscoveryStats | None,
    case_collection_data: dict[str, CaseCollectionLogData] | None,
) -> None:
    """Validate and record one discovered execution directory."""
    if stats is not None:
        stats["execution_dirs_scanned"] += 1

    case_path = str(case_dir.resolve())
    log_data = _get_case_collection_log_data(case_path, case_collection_data)
    if log_data is not None:
        log_data.execution_count_total += 1

    rejection_decision = _validate_execution_dir(
        case_dir,
        execution_id,
        metadata_locator=metadata_locator,
        stats=stats,
    )
    if rejection_decision is not None:
        if log_data is not None:
            log_data.rejected_decisions.append(rejection_decision)

        return

    if stats is not None:
        stats["execution_dirs_accepted"] += 1

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
    except FileNotFoundError as exc:
        if stats is not None:
            stats["skipped_incomplete"] += 1
            stats["rejected_incomplete_execution_ids"] += 1

        return _build_rejected_execution_decision(
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            reason="incomplete",
            exc=exc,
        )
    except ValueError as exc:
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
            stats["skipped_invalid"] += 1
            stats["rejected_invalid_execution_ids"] += 1

        return _build_rejected_execution_decision(
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            reason="invalid",
            exc=exc,
        )


def _log_execution_collection_outcomes(
    case_collection_data: dict[str, CaseCollectionLogData],
    state: dict[str, Any],
    candidates: list[IngestionCandidate],
    discovery_stats: DiscoveryStats,
    *,
    archive_root: Path,
) -> None:
    """Emit one contiguous decision block for each discovered case."""
    case_state = state.get("cases", {})
    if not isinstance(case_state, dict):
        case_state = {}

    selected_new_ids_by_case = {
        candidate.case_path: set(candidate.new_execution_ids)
        for candidate in candidates
    }

    for case_path in sorted(case_collection_data):
        log_data = case_collection_data[case_path]
        case_label = _case_log_label(case_path, archive_root)
        current_case_state = case_state.get(case_path, {})
        if not isinstance(current_case_state, dict):
            current_case_state = {}

        processed_ids = _case_state_processed_ids(current_case_state)
        valid_execution_ids = sorted(log_data.valid_execution_ids)
        new_ids = set(valid_execution_ids) - processed_ids
        selected_new_ids = selected_new_ids_by_case.get(case_path, set())
        existing_ids = sorted(set(valid_execution_ids) & processed_ids)
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

        _log_event(
            "case_collection_begin",
            {
                "case": case_label,
                "execution_count_total": log_data.execution_count_total,
                "execution_count_valid": len(valid_execution_ids),
                "execution_count_rejected_incomplete": rejected_incomplete,
                "execution_count_rejected_invalid": rejected_invalid,
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
                "deferred": len(deferred_ids),
            },
        )


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


def _build_ingestion_candidates(
    scan_results: list[CaseScanResult],
    state: dict[str, Any],
    max_cases_per_run: int | None,
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
    case_state = state.get("cases", {})
    if not isinstance(case_state, dict):
        case_state = {}

    candidates: list[IngestionCandidate] = []

    for scan in sorted(scan_results, key=lambda item: item.case_path):
        current_case_state = case_state.get(scan.case_path, {})

        if not isinstance(current_case_state, dict):
            current_case_state = {}

        processed_ids = _case_state_processed_ids(current_case_state)
        new_ids = sorted(set(scan.execution_ids) - processed_ids)

        if not new_ids:
            continue

        candidates.append(
            IngestionCandidate(
                case_path=scan.case_path,
                execution_ids=scan.execution_ids,
                new_execution_ids=new_ids,
                fingerprint=scan.fingerprint,
            )
        )

        if max_cases_per_run is not None and len(candidates) >= max_cases_per_run:
            break

    return candidates


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
            "deferred_execution_ids": summary_fields["deferred_execution_ids"],
        },
    )


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
        Machine label attached to ingested simulations.
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
        Machine label attached to ingested simulations.
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

    return {
        "version": STATE_VERSION,
        "cases": cases,
        "updated_at": _utc_now_iso(),
    }


def _is_transient_status(status_code: int | None) -> bool:
    """Return whether an HTTP status code is retriable.

    Parameters
    ----------
    status_code : int | None
        HTTP status code from a failed request.

    Returns
    -------
    bool
        ``True`` when the status should be retried.
    """
    return status_code in TRANSIENT_HTTP_STATUS_CODES


def _fresh_state() -> dict[str, Any]:
    """Build a default empty ingestion state structure.

    Returns
    -------
    dict[str, Any]
        Fresh state payload with version and timestamp fields.
    """
    return {
        "version": STATE_VERSION,
        "cases": {},
        "updated_at": _utc_now_iso(),
    }


def _record_successful_case(
    state: dict[str, Any],
    candidate: IngestionCandidate,
) -> None:
    """Update persisted state after a successful case ingestion.

    Parameters
    ----------
    state : dict[str, Any]
        Mutable ingestion state payload.
    candidate : IngestionCandidate
        Candidate that was successfully ingested.
    """
    cases = state.setdefault("cases", {})
    if not isinstance(cases, dict):
        cases = {}
        state["cases"] = cases

    cases[candidate.case_path] = {
        "fingerprint": candidate.fingerprint,
        "processed_execution_ids": candidate.execution_ids,
        "last_ingested_at": _utc_now_iso(),
    }


def _compute_case_fingerprint(execution_ids: list[str]) -> str:
    """Compute a deterministic SHA-256 fingerprint for execution IDs.

    Parameters
    ----------
    execution_ids : list[str]
        Execution IDs for one case.

    Returns
    -------
    str
        SHA-256 hex digest of newline-delimited execution IDs.
    """
    digest = hashlib.sha256()

    for execution_id in execution_ids:
        digest.update(execution_id.encode("utf-8"))
        digest.update(b"\n")

    return digest.hexdigest()


def _case_state_processed_ids(case_state: dict[str, Any]) -> set[str]:
    """Extract processed execution IDs from one case state entry.

    Parameters
    ----------
    case_state : dict[str, Any]
        State dictionary for one case.

    Returns
    -------
    set[str]
        Sanitized set of processed execution IDs.
    """
    raw_ids = case_state.get("processed_execution_ids", [])
    if not isinstance(raw_ids, list):
        return set()

    return {value for value in raw_ids if isinstance(value, str)}


def _new_discovery_stats() -> DiscoveryStats:
    """Return an initialized discovery stats dictionary."""
    return {
        "execution_dirs_scanned": 0,
        "execution_dirs_accepted": 0,
        "skipped_incomplete": 0,
        "skipped_invalid": 0,
        "accepted_execution_ids": 0,
        "rejected_existing_execution_ids": 0,
        "rejected_incomplete_execution_ids": 0,
        "rejected_invalid_execution_ids": 0,
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


def _render_log_value(value: Any) -> str:
    """Render one log field value as a readable scalar string.

    Parameters
    ----------
    value : Any
        Field value to serialize.

    Returns
    -------
    str
        Human-readable value string suitable for key-value log output.
    """
    if isinstance(value, (int, float, bool)) or value is None:
        return json.dumps(value)

    if isinstance(value, str):
        if re.fullmatch(r"[A-Za-z0-9._:/+\-@]+", value):
            return value
        return json.dumps(value)

    return json.dumps(value, sort_keys=True)


def _case_log_label(case_path: str, archive_root: Path | str) -> str:
    """Return an archive-root-relative case label for human-facing INFO logs."""
    case = Path(case_path)
    root = Path(archive_root)

    try:
        return str(case.relative_to(root))
    except ValueError:
        return case_path


def _log_startup_configuration(
    config: IngestorConfig,
    endpoint_url: str,
    state_endpoint_url: str,
) -> None:
    """Log sanitized runtime configuration for one ingestor run.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.
    endpoint_url : str
        Fully qualified ingestion endpoint URL.
    """
    _log_event("startup_configuration_begin")
    _log_event(
        "startup_configuration_api",
        {
            "api_base_url": config.api_base_url,
            "endpoint_url": endpoint_url,
            "state_endpoint_url": state_endpoint_url,
        },
    )
    _log_event(
        "startup_configuration_paths",
        {"archive_root": str(config.archive_root)},
    )
    _log_event(
        "startup_configuration_runtime",
        {
            "machine_name": config.machine_name,
            "dry_run": config.dry_run,
            "max_cases_per_run": config.max_cases_per_run,
            "max_attempts": config.max_attempts,
            "request_timeout_seconds": config.request_timeout_seconds,
        },
    )
    _log_event(
        "startup_configuration_auth",
        {"has_api_token": bool(config.api_token)},
    )
    _log_event("startup_configuration_end")


def _ordered_event_fields(event: str, fields: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return deterministic event fields using event-specific priority order."""
    ordered: list[tuple[str, Any]] = []
    seen: set[str] = set()

    for key in EVENT_FIELD_ORDER.get(event, ()):
        if key in fields:
            ordered.append((key, fields[key]))
            seen.add(key)

    for key in sorted(fields):
        if key in seen:
            continue

        ordered.append((key, fields[key]))

    return ordered


def _log_event(event: str, fields: dict[str, Any] | None = None) -> None:
    """Emit one key-value log record for an ingestion event.

    Parameters
    ----------
    event : str
        Event name.
    fields : dict[str, Any] | None, optional
        Additional event fields serialized into key-value pairs.
    """
    fields = {} if fields is None else fields
    parts = [f"event={event}"]

    for key, value in _ordered_event_fields(event, fields):
        parts.append(f"{key}={_render_log_value(value)}")

    logger.info(" ".join(parts))


def _utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Returns
    -------
    str
        Current UTC time with timezone offset.
    """
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
