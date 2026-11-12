"""Scheduled job failure details and launcher start/finish health reports.

Ingestion modules call ``record_failure`` to leave the run's first failure in
``SIMBOARD_JOB_STATUS_FILE``. The launcher then runs this module to report the
run start and finish. Reporting never raises and always exits successfully so
it cannot stop ingestion or replace its exit code.

Usage:
    python -m app.scripts.ingestion.job_health start
    python -m app.scripts.ingestion.job_health finish --exit-code <code>
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Literal

from app.api.version import API_BASE
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionRequestError,
    _log_event,
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
        "message": message[:MESSAGE_MAX_LENGTH],
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", choices=["start", "finish"])
    parser.add_argument("--exit-code", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        _send_report(args.event, args.exit_code)
    except Exception as exc:
        # Log only metadata: exception messages may include response bodies.
        _log_event(
            "job_report_failed",
            {
                "report": args.event,
                "error_type": type(exc).__name__,
                "status_code": getattr(exc, "code", None),
            },
        )
    else:
        _log_event("job_report_sent", {"report": args.event})

    return 0


def _send_report(event: str, exit_code: int) -> None:
    token = os.environ["SIMBOARD_API_TOKEN"]
    payload: dict[str, Any] = {"started_at": os.environ["SIMBOARD_JOB_STARTED_AT"]}
    if event == "finish":
        payload.update(
            finished_at=datetime.now(timezone.utc).isoformat(),
            exit_code=exit_code,
            failure=_read_failure(exit_code, token),
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


def _read_failure(exit_code: int, token: str) -> dict[str, Any] | None:
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
    message = str(failure.get("message", ""))
    if token:
        message = message.replace(token, "[redacted]")
    failure["message"] = message[:MESSAGE_MAX_LENGTH]

    return failure


if __name__ == "__main__":
    raise SystemExit(main())
