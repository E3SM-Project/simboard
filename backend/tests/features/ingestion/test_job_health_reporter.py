"""Scheduled job failure handoff and best-effort launcher health reports."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    record_upload_failures,
)

TOKEN = "sbk_secret"
RUN_ID = "0b5c1f8e-3f63-4f0b-9a57-0fd3c2c6a8d1"


@pytest.fixture
def status_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "job-status.json"
    monkeypatch.setenv("SIMBOARD_JOB_STATUS_FILE", str(path))

    return path


@pytest.fixture
def upload_failures_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "job-upload-failures.json"
    monkeypatch.setenv("SIMBOARD_JOB_UPLOAD_FAILURES_FILE", str(path))

    return path


@pytest.fixture
def report_env(
    monkeypatch: pytest.MonkeyPatch, status_file: Path, upload_failures_file: Path
) -> None:
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org/")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", TOKEN)
    monkeypatch.setenv("SIMBOARD_JOB_ID", "chrysalis-staging")
    monkeypatch.setenv("SIMBOARD_JOB_RUN_ID", RUN_ID)
    monkeypatch.setenv("SIMBOARD_JOB_STARTED_AT", "2026-01-02T00:00:00Z")
    monkeypatch.setenv("MACHINE_NAME", "chrysalis")
    monkeypatch.setenv("SIMBOARD_JOB_SCAN_MODE", "staging")


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


def test_tokens_are_redacted_before_truncation(monkeypatch, status_file: Path):
    monkeypatch.setenv("SIMBOARD_API_TOKEN", TOKEN)

    record_failure("api_request", "x" * 495 + TOKEN)

    message = json.loads(status_file.read_text())["message"]
    assert message == "x" * 495 + "[reda"


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


def test_upload_failures_keep_complete_counts_and_bounded_cases(
    monkeypatch, upload_failures_file: Path
):
    monkeypatch.setenv("SIMBOARD_API_TOKEN", TOKEN)
    timed_out = {
        "case_path": "/archive/timed-out",
        "status_code": None,
        "attempts": 3,
        "message": f"URL error: {TOKEN} " + "x" * 300,
    }
    rejected = {
        "case_path": "/archive/too-large",
        "status_code": 413,
        "attempts": 1,
        "message": "HTTP 413: <html>\n  <title>Too Large</title>\n</html>",
    }

    record_upload_failures([timed_out] + [rejected] * 50)

    report = json.loads(upload_failures_file.read_text())
    assert report["counts"] == {"network": 1, "413": 50}
    assert report["truncated"] is True
    assert len(report["cases"]) == 50
    assert report["cases"][0] == {
        **timed_out,
        "message": ("URL error: [redacted] " + "x" * 300)[:200],
    }
    assert report["cases"][1] == {
        **rejected,
        "message": "HTTP 413: <html> <title>Too Large</title> </html>",
    }


def test_upload_failures_are_recorded_only_when_present(
    monkeypatch, tmp_path: Path, upload_failures_file: Path
):
    record_upload_failures([])
    monkeypatch.delenv("SIMBOARD_JOB_UPLOAD_FAILURES_FILE")
    record_upload_failures(
        [{"case_path": "/c", "status_code": 500, "attempts": 3, "message": "x"}]
    )

    assert list(tmp_path.iterdir()) == []


def test_start_report_targets_the_job_run(report_env, sent, events):
    assert main(["start"]) == 0

    [(request, timeout)] = sent
    assert request.get_method() == "PUT"
    assert request.full_url == (
        "https://api.example.org/api/v1/ingestions/jobs/chrysalis-staging"
        f"/runs/{RUN_ID}/start"
    )
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert json.loads(request.data) == {
        "machine_name": "chrysalis",
        "scan_mode": "staging",
        "started_at": "2026-01-02T00:00:00Z",
    }
    assert timeout == job_health.REQUEST_TIMEOUT_SECONDS
    assert events == [("job_report_sent", {"report": "start"})]


def test_scan_mode_falls_back_to_the_ingestor_setting(report_env, sent, monkeypatch):
    monkeypatch.delenv("SIMBOARD_JOB_SCAN_MODE")
    monkeypatch.setenv("SCAN_MODE", " Archive ")

    main(["start"])

    assert json.loads(sent[0][0].data)["scan_mode"] == "archive"


def test_successful_finish_has_no_failure(report_env, sent, status_file):
    record_failure("unexpected", "recovered")

    main(["finish", "--exit-code", "0"])

    payload = json.loads(sent[0][0].data)
    assert payload["exit_code"] == 0
    assert payload["failure"] is None
    assert payload["upload_failures"] is None
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


def test_failed_finish_sends_recorded_upload_failures(report_env, sent):
    failure = {"case_path": "/c", "status_code": 422, "attempts": 1, "message": "x"}
    record_upload_failures([failure])

    main(["finish", "--exit-code", "1"])

    assert json.loads(sent[0][0].data)["upload_failures"] == {
        "counts": {"422": 1},
        "cases": [failure],
        "truncated": False,
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


@pytest.fixture
def fake_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    module_dir = tmp_path / "modules"
    module_dir.mkdir()
    (module_dir / "fake_job.py").write_text(
        "import os, sys\n"
        "path = os.environ.get('SIMBOARD_JOB_STATUS_FILE')\n"
        "if path:\n"
        "    with open(path, 'x') as status_file:\n"
        '        status_file.write(\'{"reason": "filesystem", "message": "disk"}\')\n'
        "path = os.environ.get('SIMBOARD_JOB_UPLOAD_FAILURES_FILE')\n"
        "if path:\n"
        "    with open(path, 'w') as upload_failures_file:\n"
        '        upload_failures_file.write(\'{"counts": {"500": 1}}\')\n'
        "sys.exit(3)\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(module_dir))

    return "fake_job"


def test_run_reports_a_live_scheduled_module(
    report_env, sent, monkeypatch, fake_module
):
    monkeypatch.setenv("DRY_RUN", "false")

    assert main(["run", fake_module]) == 3

    start, finish = (json.loads(request.data) for request, _ in sent)
    start_url, finish_url = (request.full_url for request, _ in sent)
    assert start_url.endswith("/start")
    assert finish_url == start_url.removesuffix("/start") + "/finish"
    assert RUN_ID not in start_url
    assert finish["started_at"] == start["started_at"]
    assert finish["exit_code"] == 3
    assert finish["failure"] == {"reason": "filesystem", "message": "disk"}
    assert finish["upload_failures"] == {"counts": {"500": 1}}
    for env in ("SIMBOARD_JOB_STATUS_FILE", "SIMBOARD_JOB_UPLOAD_FAILURES_FILE"):
        assert not Path(job_health.os.environ[env]).exists()


@pytest.mark.parametrize(
    ("dry_run", "job_id"), [(None, "chrysalis-staging"), ("false", None)]
)
def test_run_only_reports_live_scheduled_jobs(
    report_env, sent, monkeypatch, fake_module, dry_run, job_id
):
    for key, value in (("DRY_RUN", dry_run), ("SIMBOARD_JOB_ID", job_id)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    assert main(["run", fake_module]) == 3
    assert sent == []


def test_run_keeps_the_module_exit_code_when_reports_fail(
    report_env, monkeypatch, events, fake_module
):
    def failing_urlopen(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(job_health.urllib.request, "urlopen", failing_urlopen)
    monkeypatch.setenv("DRY_RUN", "false")

    assert main(["run", fake_module]) == 3
    assert [event for event, _ in events] == ["job_report_failed"] * 2


def test_run_forwards_termination_to_the_module(tmp_path: Path, monkeypatch):
    received: list[tuple[str, dict]] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, json.loads(body)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ready = tmp_path / "ready"
    (tmp_path / "sleeper.py").write_text(
        "import pathlib, sys, time\n"
        f"pathlib.Path({str(ready)!r}).touch()\n"
        "time.sleep(30)\n"
    )
    backend_dir = Path(__file__).resolve().parents[3]
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "DRY_RUN": "false",
        "SIMBOARD_JOB_ID": "spin-perlmutter-staging",
        "MACHINE_NAME": "perlmutter",
        "SCAN_MODE": "staging",
        "SIMBOARD_API_TOKEN": TOKEN,
        "SIMBOARD_API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "app.scripts.ingestion.job_health", "run", "sleeper"],
        cwd=backend_dir,
        env=env,
    )
    deadline = time.monotonic() + 20
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    process.send_signal(signal.SIGTERM)

    try:
        assert process.wait(timeout=20) == 128 + signal.SIGTERM
    finally:
        server.shutdown()
    assert [path.rsplit("/", 1)[-1] for path, _ in received] == ["start", "finish"]
    assert received[1][1]["exit_code"] == 143
    assert received[1][1]["failure"]["reason"] == "unexpected"
