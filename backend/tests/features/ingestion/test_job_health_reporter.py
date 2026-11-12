"""Scheduled job failure handoff and best-effort launcher health reports."""

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.scripts.ingestion import job_health
from app.scripts.ingestion.archive_client import _retry_failure_event_fields
from app.scripts.ingestion.archive_ingestor_core import IngestionRequestError
from app.scripts.ingestion.job_health import (
    main,
    record_exception,
    record_failure,
    record_request_failure,
)

TOKEN = "sbk_secret"
RUN_ID = "0b5c1f8e-3f63-4f0b-9a57-0fd3c2c6a8d1"


@pytest.fixture
def status_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "job-status.json"
    monkeypatch.setenv("SIMBOARD_JOB_STATUS_FILE", str(path))

    return path


@pytest.fixture
def report_env(monkeypatch: pytest.MonkeyPatch, status_file: Path) -> None:
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org/")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", TOKEN)
    monkeypatch.setenv("SIMBOARD_JOB_ID", "chrysalis-staging")
    monkeypatch.setenv("SIMBOARD_JOB_RUN_ID", RUN_ID)
    monkeypatch.setenv("SIMBOARD_JOB_STARTED_AT", "2026-01-02T00:00:00Z")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[urllib.request.Request, int]]:
    requests: list[tuple[urllib.request.Request, int]] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        requests.append((request, timeout))
        return _Response()

    monkeypatch.setattr(job_health.urllib.request, "urlopen", fake_urlopen)

    return requests


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        job_health, "_log_event", lambda event, fields: logged.append((event, fields))
    )

    return logged


def test_record_failure_is_a_no_op_without_a_status_file(monkeypatch, tmp_path):
    monkeypatch.delenv("SIMBOARD_JOB_STATUS_FILE", raising=False)

    record_failure("unexpected", "boom")

    assert list(tmp_path.iterdir()) == []


def test_first_bounded_failure_wins(status_file: Path):
    record_request_failure(
        IngestionRequestError("x" * 600, status_code=503, transient=True)
    )
    record_exception(OSError("disk"), "OSError: disk")

    assert json.loads(status_file.read_text()) == {
        "reason": "api_request",
        "message": "x" * 500,
        "status_code": 503,
        "transient": True,
    }


@pytest.mark.parametrize(
    ("exc", "reason"),
    [(PermissionError("denied"), "filesystem"), (ValueError(), "unexpected")],
)
def test_exceptions_are_classified(status_file: Path, exc: Exception, reason: str):
    record_exception(exc, "scan failed")

    assert json.loads(status_file.read_text())["reason"] == reason


def test_only_final_request_failures_are_recorded(status_file: Path):
    exc = IngestionRequestError("HTTP 503", status_code=503, transient=True)

    _retry_failure_event_fields(exc, 1, 3, include_transient=True)
    assert not status_file.exists()

    _retry_failure_event_fields(exc, 3, 3, include_transient=True)
    assert json.loads(status_file.read_text())["status_code"] == 503


def test_start_report_targets_the_job_run(report_env, sent, events):
    assert main(["start"]) == 0

    [(request, timeout)] = sent
    assert request.get_method() == "PUT"
    assert request.full_url == (
        "https://api.example.org/api/v1/ingestions/jobs/chrysalis-staging"
        f"/runs/{RUN_ID}/start"
    )
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert json.loads(request.data) == {"started_at": "2026-01-02T00:00:00Z"}
    assert timeout == job_health.REQUEST_TIMEOUT_SECONDS
    assert events == [("job_report_sent", {"report": "start"})]


def test_successful_finish_has_no_failure(report_env, sent, status_file):
    record_failure("unexpected", "recovered")

    main(["finish", "--exit-code", "0"])

    payload = json.loads(sent[0][0].data)
    assert payload["exit_code"] == 0
    assert payload["failure"] is None
    assert payload["finished_at"]


def test_failed_finish_without_details_is_unexpected(report_env, sent):
    main(["finish", "--exit-code", "2"])

    assert json.loads(sent[0][0].data)["failure"] == {
        "reason": "unexpected",
        "message": "Exited with code 2.",
    }


def test_failed_finish_sends_recorded_failure_without_credentials(
    report_env, sent, status_file
):
    record_failure(
        "api_request", f"HTTP 401: bad token {TOKEN}", status_code=401, transient=False
    )

    main(["finish", "--exit-code", "1"])

    assert json.loads(sent[0][0].data)["failure"] == {
        "reason": "api_request",
        "message": "HTTP 401: bad token [redacted]",
        "status_code": 401,
        "transient": False,
    }


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        urllib.error.URLError("unreachable"),
        urllib.error.HTTPError("url", 503, "unavailable", {}, None),
    ],
)
def test_report_failures_never_fail_the_reporter(
    report_env, monkeypatch, events, error
):
    def failing_urlopen(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(job_health.urllib.request, "urlopen", failing_urlopen)

    assert main(["finish", "--exit-code", "1"]) == 0
    [(event, fields)] = events
    assert event == "job_report_failed"
    assert fields["error_type"] == type(error).__name__


def test_missing_configuration_never_fails_the_reporter(monkeypatch, events):
    monkeypatch.delenv("SIMBOARD_API_TOKEN", raising=False)

    assert main(["start"]) == 0
    assert events[0][0] == "job_report_failed"
