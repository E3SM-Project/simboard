"""Scan NERSC archives and trigger SimBoard path-based ingestion.

This script is intended for scheduled execution (for example, a CronJob)
against a bind-mounted performance archive. Runtime configuration is read
from environment variables (for example ``SIMBOARD_API_BASE_URL``,
``SIMBOARD_API_TOKEN``, ``PERF_ARCHIVE_ROOT``, ``STATE_PATH``, and
``DRY_RUN``).

Each run executes four phases:

1. Discover parseable execution directories grouped by case path.
2. Compare discovered execution IDs against persisted per-case state.
3. Submit one ingestion request per changed case with retry/backoff.
4. Persist successful case state for idempotent future runs.

The state file stores per-case execution IDs and fingerprints so unchanged
cases are skipped across runs. Structured event logs are emitted for startup,
scan progress, candidate processing, and run summaries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from app.api.version import API_BASE
from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.parser import _locate_metadata_files

logger = _setup_custom_logger(__name__)
logger.setLevel(logging.INFO)

EXECUTION_DIR_PATTERN = re.compile(r"\d+\.\d+-\d+$")
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
STATE_VERSION = 1

DEFAULT_API_BASE_URL = "http://backend:8000"
DEFAULT_ARCHIVE_ROOT = "/performance_archive"
DEFAULT_MACHINE_NAME = "perlmutter"
DEFAULT_STATE_PATH = "/tmp/simboard-ingestion/state.json"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 60
MAX_SKIP_DETAIL_LOGS = 20
MAX_DRY_RUN_CANDIDATE_LOGS = 20


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

    api_base_url: str
    api_token: str
    archive_root: Path
    machine_name: str
    state_path: Path
    dry_run: bool
    max_cases_per_run: int | None
    max_attempts: int
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
            "state_path": str(config.state_path),
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
    state_path = Path(os.getenv("STATE_PATH", DEFAULT_STATE_PATH)).resolve()
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
        state_path=state_path,
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
    _log_startup_configuration(config, endpoint_url=endpoint_url)

    if not config.archive_root.is_dir():
        _log_event(
            "archive_root_missing",
            {"archive_root": str(config.archive_root)},
        )
        return 1

    if not config.dry_run and not config.api_token:
        _log_event("configuration_error", {"error": "SIMBOARD_API_TOKEN is required"})
        return 1

    scan_results, candidates, discovery_stats, state = _scan_archive(
        config,
        metadata_locator=metadata_locator,
    )

    _log_event(
        "scan_completed",
        {
            "archive_root": str(config.archive_root),
            "discovered_cases": len(scan_results),
            "candidate_cases": len(candidates),
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
            discovery_stats,
        )

    return _handle_ingest_run(
        candidates,
        scan_results,
        config,
        endpoint_url,
        state,
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


def _scan_archive(
    config: IngestorConfig,
    metadata_locator: Callable[[str], object],
) -> tuple[
    list[CaseScanResult], list[IngestionCandidate], DiscoveryStats, dict[str, Any]
]:
    """Load state and compute scan results, candidates, and discovery counters.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.
    metadata_locator : Callable[[str], object]
        Validation callable used during execution discovery.

    Returns
    -------
    tuple[list[CaseScanResult], list[IngestionCandidate], DiscoveryStats, dict[str, Any]]
        Scan results, candidate list, discovery counters, and mutable state payload.
    """
    state = _load_state(config.state_path)
    discovery_stats = _new_discovery_stats()
    grouped_executions = _discover_case_executions(
        config.archive_root, metadata_locator=metadata_locator, stats=discovery_stats
    )
    scan_results = _build_case_scan_results(grouped_executions)

    candidates = _build_ingestion_candidates(
        scan_results, state, max_cases_per_run=config.max_cases_per_run
    )

    return scan_results, candidates, discovery_stats, state


def _discover_case_executions(
    archive_root: Path,
    metadata_locator: Callable[[str], object] = _locate_metadata_files,
    stats: DiscoveryStats | None = None,
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

    Returns
    -------
    dict[str, list[str]]
        Mapping of absolute case directory paths to sorted execution IDs.
    """
    grouped: dict[str, set[str]] = {}
    skip_log_state = {"logged": 0, "suppressed": 0}
    if stats is not None:
        stats.setdefault("execution_dirs_scanned", 0)
        stats.setdefault("execution_dirs_accepted", 0)
        stats.setdefault("skipped_incomplete", 0)
        stats.setdefault("skipped_invalid", 0)

    for dirpath, dirnames, _ in os.walk(archive_root):
        for dirname in dirnames:
            if not EXECUTION_DIR_PATTERN.fullmatch(dirname):
                continue
            if stats is not None:
                stats["execution_dirs_scanned"] += 1

            case_dir = Path(dirpath)
            if not _validate_execution_dir(
                case_dir,
                dirname,
                metadata_locator=metadata_locator,
                stats=stats,
                skip_log_state=skip_log_state,
            ):
                continue

            if stats is not None:
                stats["execution_dirs_accepted"] += 1
            grouped.setdefault(str(case_dir.resolve()), set()).add(dirname)

    if skip_log_state["suppressed"]:
        _log_event(
            "execution_skip_logs_suppressed",
            {
                "suppressed_count": skip_log_state["suppressed"],
                "detail_log_limit": MAX_SKIP_DETAIL_LOGS,
            },
        )

    return {case_path: sorted(exec_ids) for case_path, exec_ids in grouped.items()}


def _validate_execution_dir(
    case_dir: Path,
    execution_id: str,
    metadata_locator: Callable[[str], object],
    stats: DiscoveryStats | None,
    skip_log_state: dict[str, int],
) -> bool:
    """Validate execution directory metadata presence and log skips.

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
    skip_log_state : dict[str, int]
        Mutable counters tracking logged and suppressed skip detail events.

    Returns
    -------
    bool
        ``True`` when execution metadata is valid; otherwise ``False``.
    """
    execution_dir = case_dir / execution_id

    try:
        metadata_locator(str(execution_dir))

        return True
    except FileNotFoundError as exc:
        if stats is not None:
            stats["skipped_incomplete"] += 1

        _log_execution_skip_detail(
            "execution_skipped_incomplete",
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            error=str(exc),
            skip_log_state=skip_log_state,
        )
    except ValueError as exc:
        if stats is not None:
            stats["skipped_invalid"] += 1

        _log_execution_skip_detail(
            "execution_skipped_invalid",
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            error=str(exc),
            skip_log_state=skip_log_state,
        )
    except OSError as exc:
        if stats is not None:
            stats["skipped_invalid"] += 1

        _log_execution_skip_detail(
            "execution_skipped_invalid",
            case_path=str(case_dir.resolve()),
            execution_id=execution_id,
            error=f"{exc.__class__.__name__}: {exc}",
            skip_log_state=skip_log_state,
        )

    return False


def _log_execution_skip_detail(
    event: str,
    case_path: str,
    execution_id: str,
    error: str,
    skip_log_state: dict[str, int],
) -> None:
    """Log one execution skip detail or increment suppressed counter.

    Parameters
    ----------
    event : str
        Skip event name.
    case_path : str
        Absolute case path.
    execution_id : str
        Execution identifier.
    error : str
        Skip reason message.
    skip_log_state : dict[str, int]
        Mutable counters for emitted and suppressed detail logs.
    """
    if skip_log_state["logged"] < MAX_SKIP_DETAIL_LOGS:
        _log_event(
            event,
            {
                "case_path": case_path,
                "execution_id": execution_id,
                "error": error,
            },
        )
        skip_log_state["logged"] += 1

        return

    skip_log_state["suppressed"] += 1


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
    discovery_stats: DiscoveryStats,
) -> int:
    """Emit dry-run candidate logs and completion summaries.

    Parameters
    ----------
    candidates : list[IngestionCandidate]
        Selected ingestion candidates.
    scan_results : list[CaseScanResult]
        Discovered case scan results.
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
                    "case_path": candidate.case_path,
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
            "candidate_cases": len(candidates),
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
        },
    )
    _log_summary_table(
        "dry_run_summary",
        rows=[
            ("mode", "dry-run"),
            ("discovered_cases", len(scan_results)),
            ("candidate_cases", len(candidates)),
            *_common_summary_rows(discovery_stats),
            ("candidate_logs_emitted", logged_candidates),
            ("candidate_logs_suppressed", suppressed_candidates),
        ],
    )
    return 0


def _handle_ingest_run(
    candidates: list[IngestionCandidate],
    scan_results: list[CaseScanResult],
    config: IngestorConfig,
    endpoint_url: str,
    state: dict[str, Any],
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

    _save_state(config.state_path, state)

    _log_event(
        "run_completed",
        {
            "scanned_cases": len(scan_results),
            "candidate_cases": len(candidates),
            "success_count": success_count,
            "failure_count": failure_count,
            "execution_dirs_scanned": discovery_stats["execution_dirs_scanned"],
            "execution_dirs_accepted": discovery_stats["execution_dirs_accepted"],
            "skipped_incomplete": discovery_stats["skipped_incomplete"],
            "skipped_invalid": discovery_stats["skipped_invalid"],
            "state_path": str(config.state_path),
        },
    )
    _log_summary_table(
        "run_summary",
        rows=[
            ("mode", "ingest"),
            ("scanned_cases", len(scan_results)),
            ("candidate_cases", len(candidates)),
            ("success_count", success_count),
            ("failure_count", failure_count),
            *_common_summary_rows(discovery_stats),
            ("state_path", str(config.state_path)),
        ],
    )

    return 1 if failure_count else 0


def _common_summary_rows(
    discovery_stats: DiscoveryStats,
) -> list[tuple[str, Any]]:
    """Build summary rows shared by dry-run and ingest completion tables."""
    return [
        ("execution_dirs_scanned", discovery_stats["execution_dirs_scanned"]),
        ("execution_dirs_accepted", discovery_stats["execution_dirs_accepted"]),
        ("skipped_incomplete", discovery_stats["skipped_incomplete"]),
        ("skipped_invalid", discovery_stats["skipped_invalid"]),
    ]


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


def _load_state(state_path: Path) -> dict[str, Any]:
    """Load persisted ingestion state from disk.

    Parameters
    ----------
    state_path : Path
        Path to the JSON state file.

    Returns
    -------
    dict[str, Any]
        Loaded state or a fresh default state when unreadable.
    """
    if not state_path.exists():
        return _fresh_state()

    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log_event(
            "state_load_failed",
            {
                "state_path": str(state_path),
                "error": str(exc),
            },
        )
        return _fresh_state()

    if not isinstance(loaded, dict):
        return _fresh_state()

    if not isinstance(loaded.get("cases"), dict):
        loaded["cases"] = {}

    loaded.setdefault("version", STATE_VERSION)
    loaded.setdefault("updated_at", _utc_now_iso())

    return loaded


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    """Persist ingestion state atomically using a temporary file.

    Parameters
    ----------
    state_path : Path
        Target JSON state path.
    state : dict[str, Any]
        State payload to serialize.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now_iso()

    tmp_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(state_path)


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


def _log_startup_configuration(config: IngestorConfig, endpoint_url: str) -> None:
    """Log sanitized runtime configuration for one ingestor run.

    Parameters
    ----------
    config : IngestorConfig
        Runtime configuration values.
    endpoint_url : str
        Fully qualified ingestion endpoint URL.
    """
    _log_event("startup_configuration_begin")
    _log_summary_table(
        "startup_configuration",
        rows=[
            ("api.api_base_url", config.api_base_url),
            ("api.endpoint_url", endpoint_url),
            ("paths.archive_root", str(config.archive_root)),
            ("paths.state_path", str(config.state_path)),
            ("runtime.machine_name", config.machine_name),
            ("runtime.dry_run", config.dry_run),
            ("runtime.max_cases_per_run", config.max_cases_per_run),
            ("runtime.max_attempts", config.max_attempts),
            ("runtime.request_timeout_seconds", config.request_timeout_seconds),
            ("auth.has_api_token", bool(config.api_token)),
        ],
    )
    _log_event("startup_configuration_end")


def _log_summary_table(title: str, rows: list[tuple[str, Any]]) -> None:
    """Emit a summary table as one log line.

    Parameters
    ----------
    title : str
        Table title label.
    rows : list[tuple[str, Any]]
        Ordered list of ``(metric, value)`` summary rows.
    """
    row_pairs = [f"{metric}={_render_log_value(value)}" for metric, value in rows]
    _log_event(
        "summary_table",
        {
            "title": title,
            "rows": " | ".join(row_pairs),
            "row_count": len(rows),
        },
    )


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
    parts = [f"ts={_utc_now_iso()}", f"event={event}"]

    for key in sorted(fields):
        parts.append(f"{key}={_render_log_value(fields[key])}")

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
