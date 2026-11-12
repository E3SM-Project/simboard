"""Scheduled job failure details and start/finish health reports.

Ingestion modules call ``record_failure`` to leave the run's first failure in
``SIMBOARD_JOB_STATUS_FILE``. The site launcher reports the run start and
finish with ``start`` and ``finish``; NERSC Spin CronJobs wrap their module with
``run``, which reports live runs when ``SIMBOARD_JOB_ID`` is set and exits with
the module's exit code. Report failures are logged and never stop ingestion or
replace its exit code.

Usage:
    python -m app.scripts.ingestion.job_health start
    python -m app.scripts.ingestion.job_health finish --exit-code <code>
    python -m app.scripts.ingestion.job_health run <module>
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.api.version import API_BASE
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionRequestError,
    _log_event,
    _parse_bool,
)

FailureReason = Literal["api_request", "filesystem", "unexpected"]

STATUS_FILE_ENV = "SIMBOARD_JOB_STATUS_FILE"
MESSAGE_MAX_LENGTH = 500
REQUEST_TIMEOUT_SECONDS = 10


def record_failure(
    reason: FailureReason,
    message: str,
    *,
    status_code: int | None = None,
    transient: bool | None = None,
) -> None:
    """Record the run's first failure for the launcher's finish report."""
    path = os.environ.get(STATUS_FILE_ENV)
    if not path:
        return

    failure = {
        "reason": reason,
        # Redact before truncating so no token prefix survives the cut.
        "message": _redact(message)[:MESSAGE_MAX_LENGTH],
        "status_code": status_code,
        "transient": transient,
    }
    try:
        # Exclusive creation keeps the first (root-cause) failure.
        with open(path, "x", encoding="utf-8") as status_file:
            json.dump(failure, status_file)
    except OSError:
        pass


def record_request_failure(exc: IngestionRequestError) -> None:
    """Record a final API request failure with the client's transient flag."""
    record_failure(
        "api_request", str(exc), status_code=exc.status_code, transient=exc.transient
    )


def record_exception(exc: BaseException, message: str) -> None:
    """Record an unhandled scan exception as a filesystem or unexpected failure."""
    record_failure("filesystem" if isinstance(exc, OSError) else "unexpected", message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start")
    commands.add_parser("finish").add_argument("--exit-code", type=int, default=0)
    commands.add_parser("run").add_argument("module")
    args = parser.parse_args(argv)

    if args.command == "run":
        return run_module(args.module)

    _report(args.command, getattr(args, "exit_code", 0))

    return 0


def run_module(module: str) -> int:
    """Run ``python -m <module>``, reporting it when it is a live scheduled job."""
    live = not _parse_bool(os.environ.get("DRY_RUN"), default=True)
    if not (live and os.environ.get("SIMBOARD_JOB_ID")):
        return _run_child(module)

    run_id = str(uuid4())
    status_path = Path(tempfile.gettempdir()) / f"simboard-job-status-{run_id}.json"
    os.environ.update(
        SIMBOARD_JOB_RUN_ID=run_id,
        SIMBOARD_JOB_STARTED_AT=_utc_now(),
        SIMBOARD_JOB_STATUS_FILE=str(status_path),
    )
    _report("start")
    exit_code = _run_child(module)
    _report("finish", exit_code)
    status_path.unlink(missing_ok=True)

    return exit_code


def _report(event: str, exit_code: int = 0) -> None:
    try:
        _send_report(event, exit_code)
    except Exception as exc:
        # Log only metadata: exception messages may include response bodies.
        _log_event(
            "job_report_failed",
            {
                "report": event,
                "error_type": type(exc).__name__,
                "status_code": getattr(exc, "code", None),
            },
        )
    else:
        _log_event("job_report_sent", {"report": event})


def _run_child(module: str) -> int:
    process = subprocess.Popen([sys.executable, "-m", module])
    # Pass scheduler termination to the module so the wrapper can still finish.
    previous_handler = signal.signal(signal.SIGTERM, partial(_forward_signal, process))
    try:
        return_code = process.wait()
    finally:
        signal.signal(signal.SIGTERM, previous_handler)

    # Report signal termination as the shell does (128 + signal number).
    return return_code if return_code >= 0 else 128 - return_code


def _forward_signal(process: subprocess.Popen, signum: int, _frame: object) -> None:
    process.send_signal(signum)


def _send_report(event: str, exit_code: int) -> None:
    token = os.environ["SIMBOARD_API_TOKEN"]
    # Identity registers the job on its first report. NERSC Spin ingestion
    # secrets already set SCAN_MODE; the launcher sets SIMBOARD_JOB_SCAN_MODE.
    payload: dict[str, Any] = {
        "machine_name": os.environ["MACHINE_NAME"],
        # Normalize as the ingestor does so accepted run settings also report.
        "scan_mode": (
            os.environ.get("SIMBOARD_JOB_SCAN_MODE") or os.environ["SCAN_MODE"]
        )
        .strip()
        .lower(),
        "started_at": os.environ["SIMBOARD_JOB_STARTED_AT"],
    }
    if event == "finish":
        payload.update(
            finished_at=_utc_now(),
            exit_code=exit_code,
            failure=_read_failure(exit_code),
        )

    base_url = os.environ["SIMBOARD_API_BASE_URL"].rstrip("/")
    if not base_url.endswith(API_BASE):
        base_url = f"{base_url}{API_BASE}"
    job_id = urllib.parse.quote(os.environ["SIMBOARD_JOB_ID"], safe="")
    run_id = urllib.parse.quote(os.environ["SIMBOARD_JOB_RUN_ID"], safe="")
    request = urllib.request.Request(
        f"{base_url}/ingestions/jobs/{job_id}/runs/{run_id}/{event}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS):
        pass


def _read_failure(exit_code: int) -> dict[str, Any] | None:
    if exit_code == 0:
        return None

    failure: dict[str, Any] = {
        "reason": "unexpected",
        "message": f"Exited with code {exit_code}.",
    }
    try:
        with open(os.environ[STATUS_FILE_ENV], encoding="utf-8") as status_file:
            recorded = json.load(status_file)
        if isinstance(recorded, dict):
            failure = recorded
    except (KeyError, OSError, ValueError):
        pass

    # Never send credentials, even if an error message echoed them.
    failure["message"] = _redact(str(failure.get("message", ""))[:MESSAGE_MAX_LENGTH])

    return failure


def _redact(message: str) -> str:
    token = os.environ.get("SIMBOARD_API_TOKEN")

    return message.replace(token, "[redacted]") if token else message


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
