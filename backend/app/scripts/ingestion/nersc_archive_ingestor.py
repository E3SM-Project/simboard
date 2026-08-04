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

import time

from app.features.ingestion.parsers.parser import _locate_metadata_files
from app.scripts.ingestion.archive_client import (
    _build_archive_checkpoints_endpoint_url,
    _build_discovery_results_endpoint_url,
    _build_endpoint_url,
    _build_state_endpoint_url,
    _fetch_archive_checkpoints,
    _fetch_ingestion_state,
    _post_ingestion_request,
)
from app.scripts.ingestion.archive_discovery import _scan_archive
from app.scripts.ingestion.archive_ingestor_core import (
    ArchiveCheckpointPersistenceCallback,
    CaseSubmissionCallback,
    DiscoveryResultsPersistenceCallback,
    ExecutionDiscoveryResult,
    IngestionRequestError,
    IngestorConfig,
    MetadataLocator,
    SleepCallback,
    UnsupportedArchiveLayoutError,
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


def _case_submission_callback(
    post_request_fn: CaseSubmissionCallback | None,
) -> CaseSubmissionCallback:
    """Resolve the NERSC path-ingestion transport for this run."""
    return _post_ingestion_request if post_request_fn is None else post_request_fn


def _run_ingestor(
    config: IngestorConfig,
    metadata_locator: MetadataLocator = _locate_metadata_files,
    sleep_fn: SleepCallback = time.sleep,
    post_request_fn: CaseSubmissionCallback | None = None,
    discovery_post_request_fn: DiscoveryResultsPersistenceCallback | None = None,
    checkpoint_post_request_fn: ArchiveCheckpointPersistenceCallback | None = None,
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
    )
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


if __name__ == "__main__":
    raise SystemExit(main())
