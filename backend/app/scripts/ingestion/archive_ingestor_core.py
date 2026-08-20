"""Shared contracts and configuration for archive ingestion runners."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict, cast

from app.core.logger import _setup_custom_logger

logger = _setup_custom_logger(__name__)
logger.setLevel(logging.INFO)

TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
# Increment only for backward-incompatible persisted state changes.
STATE_VERSION = 1
# NERSC Spin backend service DNS name.
DEFAULT_API_BASE_URL = "http://backend:8000"
DEFAULT_PERF_ARCHIVE_ROOT = "/performance_archive"
DEFAULT_OLD_PERF_ARCHIVE_ROOT = "/OLD_PERF"
DEFAULT_MACHINE_NAME = "perlmutter"
DEFAULT_SCAN_MODE = "staging"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 60
DISCOVERY_RESULT_BATCH_SIZE = 500
DISCOVERY_OUTCOME_PRECEDENCE = {
    "rejected_incomplete": 0,
    "rejected_invalid": 1,
    "accepted": 2,
}
MAX_DRY_RUN_CANDIDATE_LOGS = 20
DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES = 250
ARCHIVE_SCAN_MODES = {"staging", "archive"}
ARCHIVE_FILTER_VALUE_PATTERN = re.compile(r"^(?P<year>\d{4})(?:-(?P<month>\d{2}))?$")

# Preserve stable field ordering in structured logs.
EVENT_FIELD_ORDER: dict[str, tuple[str, ...]] = {
    "run_started": ("mode", "scan_mode", "archive_root"),
    "run_finished": ("mode", "scan_mode", "exit_code", "duration_seconds"),
    "archive_scan_started": ("scan_mode", "archive_root"),
    "archive_scan_progress": (
        "scan_mode",
        "archive_root",
        "current_dir",
        "directories_visited",
        "discovered_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_transient",
        "rejected_existing_execution_ids",
        "duration_seconds",
    ),
    "archive_scan_completed": (
        "scan_mode",
        "archive_root",
        "current_dir",
        "directories_visited",
        "discovered_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_transient",
        "rejected_existing_execution_ids",
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
        "execution_count_transient",
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
        "transient",
        "deferred",
    ),
    "scan_completed": (
        "scan_mode",
        "archive_root",
        "discovered_cases",
        "submission_qualified_cases",
        "selected_submission_cases",
        "execution_dirs_scanned",
        "execution_dirs_accepted",
        "skipped_incomplete",
        "skipped_invalid",
        "skipped_transient",
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "transient_execution_ids",
        "deferred_execution_ids",
    ),
    "dry_run_candidate": ("case", "execution_count", "new_execution_count"),
    "startup_configuration_api": (
        "api_base_url",
        "endpoint_url",
        "state_endpoint_url",
    ),
    "startup_configuration_paths": (
        "scan_mode",
        "archive_root",
        "archive_year_start",
        "archive_year_end",
    ),
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
        "skipped_transient",
    ),
    "dry_run_summary_candidates": (
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "transient_execution_ids",
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
        "skipped_transient",
    ),
    "run_summary_outcomes": (
        "success_count",
        "failure_count",
        "accepted_execution_ids",
        "rejected_existing_execution_ids",
        "rejected_incomplete_execution_ids",
        "rejected_invalid_execution_ids",
        "transient_execution_ids",
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
    "archive_created": (
        "case_path",
        "selected_execution_count",
        "archive_bytes",
        "duration_seconds",
    ),
    "case_upload_attempt": (
        "case_path",
        "attempt",
        "archive_bytes",
        "duration_seconds",
    ),
    "case_ingestion_attempt_completed": (
        "case_path",
        "attempt",
        "duration_seconds",
    ),
    "case_ingestion_retry_completed": (
        "case_path",
        "attempts",
        "duration_seconds",
    ),
}


# Runtime Models and Errors
# -------------------------


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
    # Whether this run scans the staging or archive root.
    scan_mode: Literal["staging", "archive"] = "staging"
    # Optional archive lower bound normalized to a YYYY-MM archive bucket.
    archive_year_start: str | None = None
    # Optional archive upper bound normalized to a YYYY-MM archive bucket.
    archive_year_end: str | None = None


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


class UnsupportedArchiveLayoutError(ValueError):
    """Archive layout cannot support requested filtered scan semantics."""


class DiscoveryStats(TypedDict):
    """Discovery counters captured during archive scanning."""

    execution_dirs_scanned: int
    execution_dirs_accepted: int
    skipped_incomplete: int
    skipped_invalid: int
    skipped_transient: int
    accepted_execution_ids: int
    rejected_existing_execution_ids: int
    rejected_incomplete_execution_ids: int
    rejected_invalid_execution_ids: int
    transient_execution_ids: int
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


@dataclass(frozen=True)
class ExecutionDiscoveryResult:
    """Immutable validation outcome awaiting API persistence."""

    case_identity: str
    execution_id: str
    outcome: Literal["accepted", "rejected_incomplete", "rejected_invalid"]


@dataclass
class CaseCollectionLogData:
    """Discovery and decision inputs needed to log one case block."""

    case_path: str
    execution_count_total: int = 0
    valid_execution_ids: set[str] = field(default_factory=set)
    rejected_decisions: list[ExecutionCollectionDecision] = field(default_factory=list)


@dataclass
class ArchiveSnapshotScan:
    """Filesystem snapshot units and execution identities scanned in this run."""

    archive_name: str
    eligible_keys: set[str] = field(default_factory=set)
    completed_keys: set[str] = field(default_factory=set)
    references_by_key: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    traversal_complete: bool = True


class CaseSubmissionCallback(Protocol):
    """Submit one case for ingestion."""

    def __call__(
        self,
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        /,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse: ...


class DiscoveryResultsPersistenceCallback(Protocol):
    """Persist one batch of execution discovery results."""

    def __call__(
        self,
        endpoint_url: str,
        api_token: str,
        machine_name: str,
        /,
        *,
        results: list[ExecutionDiscoveryResult],
        timeout_seconds: int,
    ) -> IngestionRequestResponse: ...


class ArchiveCheckpointPersistenceCallback(Protocol):
    """Persist one batch of completed archive snapshot checkpoints."""

    def __call__(
        self,
        endpoint_url: str,
        api_token: str,
        machine_name: str,
        /,
        *,
        archive_name: str,
        snapshot_keys: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse: ...


class MetadataLocator(Protocol):
    """Validate and locate metadata for one execution directory."""

    def __call__(self, execution_dir: str, /) -> object: ...


class SleepCallback(Protocol):
    """Pause execution for a retry delay."""

    def __call__(self, seconds: float, /) -> None: ...


class StructuredLogCallback(Protocol):
    """Emit one structured ingestion event."""

    def __call__(
        self,
        event: str,
        fields: dict[str, Any] | None = None,
    ) -> None: ...


# Configuration
# -------------


def _build_config_from_env() -> IngestorConfig:
    """Build and validate runtime config from environment variables.

    Returns
    -------
    IngestorConfig
        Validated ingestion runner configuration.

    Raises
    ------
    ValueError
        Raised when numeric options or archive range bounds are invalid.
    """
    api_base_url = os.getenv("SIMBOARD_API_BASE_URL", DEFAULT_API_BASE_URL)
    api_token = os.getenv("SIMBOARD_API_TOKEN", "")

    scan_mode = os.getenv("SCAN_MODE", DEFAULT_SCAN_MODE).strip().lower()
    if scan_mode not in ARCHIVE_SCAN_MODES:
        raise ValueError("SCAN_MODE must be either 'staging' or 'archive'")

    staging_root = Path(
        os.getenv("PERF_ARCHIVE_ROOT", DEFAULT_PERF_ARCHIVE_ROOT)
    ).resolve()

    configured_archive_root = Path(
        os.getenv("OLD_PERF_ARCHIVE_ROOT", DEFAULT_OLD_PERF_ARCHIVE_ROOT)
    ).resolve()
    archive_root = configured_archive_root if scan_mode == "archive" else staging_root

    machine_name = os.getenv("MACHINE_NAME", DEFAULT_MACHINE_NAME)
    dry_run = _parse_bool(os.getenv("DRY_RUN"), default=True)
    max_cases_per_run = _parse_optional_int(os.getenv("MAX_CASES_PER_RUN"))

    if max_cases_per_run is not None and max_cases_per_run <= 0:
        raise ValueError("MAX_CASES_PER_RUN must be greater than 0 when provided")

    max_attempts = _parse_optional_int(os.getenv("MAX_ATTEMPTS"))
    if max_attempts is None:
        max_attempts = DEFAULT_MAX_ATTEMPTS
    if max_attempts <= 0:
        raise ValueError("MAX_ATTEMPTS must be greater than 0")

    timeout_seconds = _parse_optional_int(os.getenv("REQUEST_TIMEOUT_SECONDS"))
    if timeout_seconds is None:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    if timeout_seconds <= 0:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be greater than 0")

    archive_year_start = _parse_optional_archive_bound(
        os.getenv("ARCHIVE_YEAR_START"),
        env_name="ARCHIVE_YEAR_START",
        is_end_bound=False,
    )
    archive_year_end = _parse_optional_archive_bound(
        os.getenv("ARCHIVE_YEAR_END"),
        env_name="ARCHIVE_YEAR_END",
        is_end_bound=True,
    )

    if scan_mode != "archive" and (
        archive_year_start is not None or archive_year_end is not None
    ):
        raise ValueError(
            "ARCHIVE_YEAR_START and ARCHIVE_YEAR_END require SCAN_MODE=archive"
        )

    if (
        archive_year_start is not None
        and archive_year_end is not None
        and archive_year_start > archive_year_end
    ):
        raise ValueError(
            "ARCHIVE_YEAR_START must be less than or equal to ARCHIVE_YEAR_END"
        )

    return IngestorConfig(
        api_base_url=api_base_url,
        api_token=api_token,
        archive_root=archive_root,
        machine_name=machine_name,
        scan_mode=cast(Literal["staging", "archive"], scan_mode),
        dry_run=dry_run,
        max_cases_per_run=max_cases_per_run,
        max_attempts=max_attempts,
        request_timeout_seconds=timeout_seconds,
        archive_year_start=archive_year_start,
        archive_year_end=archive_year_end,
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


def _parse_optional_archive_bound(
    value: str | None,
    *,
    env_name: str,
    is_end_bound: bool,
) -> str | None:
    """Parse an optional archive range bound into normalized YYYY-MM format."""
    if value is None:
        return None

    normalized = value.strip()
    if normalized == "":
        return None

    match = ARCHIVE_FILTER_VALUE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"{env_name} must use YYYY or YYYY-MM format")

    year = match.group("year")
    month = match.group("month")
    if month is None:
        return f"{year}-12" if is_end_bound else f"{year}-01"

    month_value = int(month)
    if month_value < 1 or month_value > 12:
        raise ValueError(f"{env_name} month must be between 01 and 12")

    return f"{year}-{month}"


# Immutable Discovery Results
# ---------------------------


def _deduplicate_discovery_results(
    results: list[ExecutionDiscoveryResult],
) -> list[ExecutionDiscoveryResult]:
    """Collapse snapshot duplicates using deterministic outcome precedence."""
    results_by_identity: dict[tuple[str, str], ExecutionDiscoveryResult] = {}
    for result in results:
        identity = (result.case_identity, result.execution_id)
        existing = results_by_identity.get(identity)
        if (
            existing is None
            or DISCOVERY_OUTCOME_PRECEDENCE[result.outcome]
            > DISCOVERY_OUTCOME_PRECEDENCE[existing.outcome]
        ):
            results_by_identity[identity] = result

    return list(results_by_identity.values())


# State and Fingerprints
# ----------------------


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
        "discovery_results": {},
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

    existing_case_state = cases.get(candidate.case_path, {})
    existing_execution_ids = (
        _case_state_processed_ids(existing_case_state)
        if isinstance(existing_case_state, dict)
        else set()
    )
    merged_execution_ids = sorted(existing_execution_ids | set(candidate.execution_ids))
    fingerprint = (
        candidate.fingerprint
        if merged_execution_ids == candidate.execution_ids
        else _compute_case_fingerprint(merged_execution_ids)
    )
    cases[candidate.case_path] = {
        "fingerprint": fingerprint,
        "processed_execution_ids": merged_execution_ids,
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


def _build_discovery_results_by_key(
    state: dict[str, Any],
) -> dict[tuple[str, str], str]:
    """Build immutable-result lookup from normalized remote state."""
    raw_results = state.get("discovery_results", {})
    if not isinstance(raw_results, dict):
        return {}

    lookup: dict[tuple[str, str], str] = {}
    for case_identity, results in raw_results.items():
        if not isinstance(case_identity, str) or not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue

            execution_id = result.get("execution_id")
            outcome = result.get("outcome")

            if isinstance(execution_id, str) and outcome in {
                "accepted",
                "rejected_incomplete",
                "rejected_invalid",
            }:
                lookup[(case_identity, execution_id)] = cast(str, outcome)

    return lookup


# Logging
# -------


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
