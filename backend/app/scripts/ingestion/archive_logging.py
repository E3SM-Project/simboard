"""Observational logging contract for ingestion command-line runners."""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

OUTCOMES = ("selected", "skipped", "incomplete", "invalid", "unreadable", "deferred")
OUTCOME_FIELDS = (
    "accepted",
    "rejected_existing",
    "rejected_incomplete",
    "rejected_invalid",
    "transient",
    "deferred",
)
# Only CLI diagnostics belong here; unrelated shared callers retain their policy.
DEBUG_EVENTS = {
    "archive_scan_started",
    "archive_scan_progress",
    "archive_scan_completed",
    "scan_completed",
    "archive_created",
    "case_upload_attempt",
    "case_ingestion_attempt_completed",
    "case_submission_details",
    "v3_ingestion_summary",
}
ERROR_EVENTS = {
    "configuration_error",
    "archive_root_missing",
    "archive_scan_failed",
    "state_fetch_failed",
    "archive_checkpoint_fetch_failed",
    "archive_checkpoint_persistence_failed",
    "discovery_results_persistence_failed",
    "case_ingestion_request_failed",
    "v3_case_missing",
}
_context: ContextVar[RunLog | None] = ContextVar("ingestion_log", default=None)
_handler: logging.Handler | None = None


@dataclass
class RunLog:
    """Reporting state; never used to drive ingestion."""

    runner: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: _utc_now())
    clock: float = field(default_factory=lambda: time.monotonic())
    dimensions: dict[str, Any] = field(default_factory=dict)
    cases: dict[str, dict[str, int]] = field(default_factory=dict)
    eligible: int | None = None
    selected: int | None = None
    succeeded: int = 0
    failed: int = 0
    discovery_complete: bool = False
    submission_finished: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize(value: Any) -> Any:
    """Remove known credentials and URL secrets before rendering any record."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.lower() in {"token", "api_token", "authorization", "password"}
            else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        token = os.getenv("SIMBOARD_API_TOKEN")
        if token:
            value = value.replace(token, "[REDACTED]")
        value = re.sub(r"(https?://)[^/\s]+@", r"\1[REDACTED]@", value)
        return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", value)
    return value


def configure(logger: logging.Logger, level_name: str | None = None) -> None:
    """Install one ingestion-only UTC console handler."""
    global _handler
    name = (
        (level_name or os.getenv("SIMBOARD_INGESTION_LOG_LEVEL", "INFO"))
        .strip()
        .upper()
    )
    levels = {
        key: getattr(logging, key)
        for key in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    }
    if name not in levels:
        raise ValueError(
            "SIMBOARD_INGESTION_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
        )
    if _handler is None or _handler not in logger.handlers:
        _handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
        formatter.converter = time.gmtime
        _handler.setFormatter(formatter)
    if _handler not in logger.handlers:
        logger.addHandler(_handler)
    logger.propagate = False
    logger.setLevel(levels[name])
    _handler.setLevel(levels[name])


def observe(event: str, fields: dict[str, Any]) -> None:
    """Collect existing event outcomes without modifying operational counters."""
    run = _context.get()
    if run is None:
        return
    if event in {"run_started", "v3_run_started"}:
        run.dimensions.update(
            scan_mode=fields.get("scan_mode", "archive"),
            dry_run=fields.get("mode") == "dry-run",
        )
    elif event == "startup_configuration_runtime":
        run.dimensions.update(
            machine=fields.get("machine_name"), dry_run=fields.get("dry_run")
        )
    elif event == "startup_configuration_paths":
        run.dimensions["scan_mode"] = fields.get("scan_mode")
    elif event == "case_collection_summary":
        counts = dict(
            zip(OUTCOMES, (int(fields[key]) for key in OUTCOME_FIELDS), strict=True)
        )
        run.cases[str(fields["case"])] = {"total": sum(counts.values()), **counts}
    elif event == "scan_completed":
        run.eligible = fields["submission_qualified_cases"]
        run.selected = fields["selected_submission_cases"]
    elif event == "case_ingested":
        run.succeeded += 1
    elif event == "case_ingestion_failed":
        run.failed += 1
    elif event == "run_completed":
        run.submission_finished = True


def scan_finished(traversal_complete: bool) -> None:
    """Record discovery completeness, including filesystem traversal gaps."""
    run = _context.get()
    if run is not None:
        run.discovery_complete = traversal_complete


def record_config(config: Any) -> None:
    """Capture validated configuration even if a later precondition fails."""
    run = _context.get()
    if run is not None:
        run.dimensions.update(
            machine=config.machine_name,
            scan_mode=config.scan_mode,
            dry_run=config.dry_run,
            archive_root=str(config.archive_root),
        )


def presentation(
    event: str, fields: dict[str, Any]
) -> tuple[str, str, int, dict[str, Any]]:
    """Translate internal events into simple public terminology."""
    category, level = "CONFIG", logging.INFO
    if event == "execution_collection_decision":
        category, level, event = "EXECUTION_DETAIL", logging.DEBUG, "execution_decision"
        outcome = {
            "new_execution": "selected",
            "already_processed": "skipped",
            "transient": "unreadable",
            "max_cases_per_run": "deferred",
        }.get(fields.get("reason"), fields.get("reason"))
        fields = {key: value for key, value in fields.items() if key != "decision"}
        fields["outcome"] = outcome
    elif event == "case_collection_summary":
        category, event = "CASE_SUMMARY", "case_discovered"
        counts = dict(
            zip(OUTCOMES, (fields[key] for key in OUTCOME_FIELDS), strict=True)
        )
        fields = {
            "case": fields["case"],
            "executions.total": sum(counts.values()),
            **{f"executions.{key}": value for key, value in counts.items()},
        }
    elif event in {"case_ingested", "case_ingestion_failed"}:
        category = "CASE_SUMMARY"
        case = fields.get("case_path")
        run = _context.get()
        if run and case and run.dimensions.get("archive_root"):
            try:
                case = str(Path(case).relative_to(run.dimensions["archive_root"]))
            except ValueError:
                pass
        fields = {
            **{key: value for key, value in fields.items() if key != "case_path"},
            "case": case,
            "outcome": "failed" if event == "case_ingestion_failed" else "succeeded",
        }
        if event == "case_ingestion_failed":
            level = logging.ERROR
        else:
            fields = {key: fields[key] for key in ("case", "outcome")}
        event = "case_submission"
    elif fields.get("retrying") or fields.get("recoverable"):
        level = logging.WARNING
    elif event in ERROR_EVENTS:
        level = logging.ERROR
    elif event in DEBUG_EVENTS:
        category, level = "EXECUTION_DETAIL", logging.DEBUG
    return category, event, level, fields


def prefix(category: str) -> str:
    run = _context.get()
    return f"{category} run_id={run.run_id}" if run else category


def has_run_context() -> bool:
    """Keep unrelated shared-helper callers outside the CLI logging policy."""
    return _context.get() is not None


def metrics(run: RunLog, exit_code: int) -> dict[str, Any]:
    """Build one canonical record from known reporting data."""
    known = run.selected is not None
    executions = {
        key: sum(case[key] for case in run.cases.values()) if known else None
        for key in ("total", *OUTCOMES)
    }
    return {
        "schema_version": 1,
        "run_id": run.run_id,
        "runner": run.runner,
        "machine": run.dimensions.get("machine"),
        "environment": os.path.basename(os.getenv("SIMBOARD_ENV_FILE", "")) or None,
        "scan_mode": run.dimensions.get("scan_mode"),
        "dry_run": run.dimensions.get("dry_run"),
        "started_at": run.started_at,
        "finished_at": _utc_now(),
        "duration_seconds": round(time.monotonic() - run.clock, 3),
        "status": "success" if exit_code == 0 else "failure",
        "exit_code": exit_code,
        "discovery_complete": run.discovery_complete,
        "submission_complete": known
        and run.submission_finished
        and not run.dimensions.get("dry_run", True)
        and run.succeeded + run.failed == run.selected,
        "executions": executions,
        "cases": {
            "found": len(run.cases) if known else None,
            "eligible": run.eligible,
            "selected": run.selected,
            "deferred": run.eligible - run.selected
            if known and run.eligible is not None
            else None,
            "succeeded": run.succeeded if known else None,
            "failed": run.failed if known else None,
            "not_attempted": run.selected - run.succeeded - run.failed
            if known
            else None,
        },
    }


def _finish(logger: logging.Logger, run: RunLog, exit_code: int) -> None:
    record = sanitize(metrics(run, exit_code))
    lines = [("Executions found", record["executions"]["total"])]
    lines.extend(
        (f"  {key.capitalize()}", record["executions"][key]) for key in OUTCOMES
    )
    lines.extend(
        (label, record["cases"][key])
        for label, key in (
            ("Cases found", "found"),
            ("Cases eligible", "eligible"),
            ("  Selected", "selected"),
            ("  Deferred", "deferred"),
            ("Selected case outcomes", "selected"),
            ("  Succeeded", "succeeded"),
            ("  Failed", "failed"),
            ("  Not attempted", "not_attempted"),
        )
    )
    for label, value in lines:
        logger.info(
            "%s %s: %s",
            prefix("RUN_SUMMARY"),
            label,
            "unavailable" if value is None else value,
        )
    logger.info(
        "%s status=%s exit_code=%s duration_seconds=%s",
        prefix("RUN_SUMMARY"),
        record["status"],
        exit_code,
        record["duration_seconds"],
    )
    logger.info(
        "%s event=run_metrics payload=%s",
        prefix("RUN_SUMMARY"),
        json.dumps(record, separators=(",", ":"), allow_nan=False),
    )


def logged_main(function: Callable[[], int]) -> Callable[[], int]:
    """Wrap CLI reporting while preserving exceptions and returned exit codes."""

    @functools.wraps(function)
    def wrapped() -> int:
        logger = logging.getLogger("app.scripts.ingestion.archive_ingestor_core")
        previous_level, previous_propagate = logger.level, logger.propagate
        previous_handlers = logger.handlers[:]
        # ``python -m`` executes as __main__; retain the actual module identity
        # so metrics from different transports do not collapse into one group.
        runner_name = getattr(
            getattr(function, "__globals__", {}).get("__spec__"),
            "name",
            function.__module__,
        )
        run = RunLog(runner_name)
        token = _context.set(run)
        try:
            try:
                configure(logger)
            except ValueError as exc:
                # Invalid logging configuration is the only new failure mode.
                try:
                    configure(logger, "INFO")
                    logger.error(
                        "CONFIG run_id=%s event=configuration_error error=%s",
                        run.run_id,
                        exc,
                    )
                    _finish(logger, run, 1)
                except Exception:
                    pass
                return 1
            except Exception:
                pass
            try:
                logger.info("%s event=invocation_started", prefix("CONFIG"))
            except Exception:
                pass
            result = function()
            try:
                _finish(logger, run, result)
            except Exception:
                # Reporting must never replace the operational outcome.
                pass
            return result
        finally:
            _context.reset(token)
            logger.handlers[:] = previous_handlers
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate

    return wrapped
