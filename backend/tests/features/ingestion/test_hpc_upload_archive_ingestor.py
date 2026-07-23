"""Tests for automated HPC upload archive ingestor runner."""

import json
import os
import runpy
import subprocess
import tarfile
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
)
from app.scripts.ingestion import hpc_upload_archive_ingestor as upload_ingestor_module
from app.scripts.ingestion import nersc_archive_ingestor as nersc_ingestor_module
from app.scripts.ingestion.hpc_upload_archive_ingestor import (
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _build_endpoint_url,
    _create_case_archive,
    _post_hpc_upload_ingestion_request,
    _run_ingestor,
)
from app.scripts.ingestion.nersc_archive_ingestor import _fresh_state


def _chrysalis_wrapper_path() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "app/scripts/ingestion/sites/chrysalis.sh"
    )


def _fake_python(tmp_path: Path) -> Path:
    python_path = tmp_path / "python"
    python_path.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "${SCAN_MODE}" "${PERF_ARCHIVE_ROOT}" '
        '"${ARCHIVE_YEAR_START-unset}" > "${CAPTURE_PATH}"\n',
        encoding="utf-8",
    )
    python_path.chmod(0o755)
    return python_path


def test_chrysalis_wrapper_requires_api_base_url(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("SIMBOARD_API_BASE_URL", None)
    env["SIMBOARD_API_TOKEN"] = "token"
    env["PYTHON_BIN"] = str(_fake_python(tmp_path))

    result = subprocess.run(
        [_chrysalis_wrapper_path()],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "SIMBOARD_API_BASE_URL must be set" in result.stderr


def test_chrysalis_wrapper_defaults_to_staging(tmp_path: Path) -> None:
    capture_path = tmp_path / "environment.txt"
    env = os.environ.copy()
    env.pop("ARCHIVE_YEAR_START", None)
    env.pop("SCAN_MODE", None)
    env["CAPTURE_PATH"] = str(capture_path)
    env["PYTHON_BIN"] = str(_fake_python(tmp_path))
    env["SIMBOARD_API_BASE_URL"] = "https://simboard.example"
    env["SIMBOARD_API_TOKEN"] = "token"

    result = subprocess.run(
        [_chrysalis_wrapper_path()],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert capture_path.read_text(encoding="utf-8").splitlines() == [
        "staging",
        "/lcrc/group/e3sm/PERF_Chrysalis/performance_archive",
        "unset",
    ]


@pytest.fixture(autouse=True)
def _stub_discovery_result_persistence(monkeypatch) -> None:
    monkeypatch.setattr(
        nersc_ingestor_module,
        "_post_discovery_results_request",
        lambda *args, **kwargs: {"status_code": 201, "body": {}},
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_archive_checkpoints",
        lambda *args, **kwargs: set(),
    )
    monkeypatch.setattr(
        nersc_ingestor_module,
        "_post_archive_checkpoints_request",
        lambda *args, **kwargs: {"status_code": 201, "body": {}},
    )


class _FakeHttpResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeHttpError(urllib.error.HTTPError):
    def __init__(self, url: str, code: int, msg: str, body: bytes) -> None:
        super().__init__(url, code, msg, hdrs=Message(), fp=None)
        self._body = body

    def read(self, amt: int = -1) -> bytes:
        return self._body if amt == -1 else self._body[:amt]


def test_build_endpoint_url() -> None:
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=Path("/archive"),
        machine_name="pm",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert _build_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/from-hpc-upload"
    )


def test_create_case_archive_packages_single_case_dir(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_a"
    execution_dir = case_dir / "100.1-1"
    execution_dir.mkdir(parents=True)
    (execution_dir / "env_run.xml.001").write_text("content")

    archive_path = _create_case_archive(str(case_dir), tmp_path)

    with tarfile.open(archive_path, "r:gz") as tar_file:
        members = tar_file.getnames()

    assert archive_path.name.endswith(".tar.gz")
    assert members
    assert all(member == "case_a" or member.startswith("case_a/") for member in members)


def test_create_case_archive_rejects_non_directory(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("payload")

    with pytest.raises(IngestionRequestError, match="Case path is not a directory"):
        _create_case_archive(str(not_a_directory), tmp_path)


def test_post_hpc_upload_ingestion_request_sends_case_path_and_processed_execution_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "100.1-1" / "metadata.txt").write_text("payload")
    captured_request: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_request.append(request)
        assert timeout == 12
        return _FakeHttpResponse(201, json.dumps({"created_count": 1}))

    monkeypatch.setattr(upload_ingestor_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_hpc_upload_ingestion_request(
        "http://backend:8000/api/v1/ingestions/from-hpc-upload",
        "token",
        str(case_dir),
        "pm",
        processed_execution_ids=["100.1-1", "101.1-1"],
        timeout_seconds=12,
    )

    assert response == {"status_code": 201, "body": {"created_count": 1}}
    assert captured_request[0].headers["Authorization"] == "Bearer token"
    content_type = captured_request[0].headers.get(
        "Content-type",
        captured_request[0].headers.get("Content-Type", ""),
    )
    assert "multipart/form-data; boundary=" in content_type
    request_body = captured_request[0].data
    assert isinstance(request_body, bytes)
    assert b'name="case_path"' in request_body
    assert str(case_dir).encode("utf-8") in request_body
    assert b'name="processed_execution_ids"' in request_body
    assert b"100.1-1" in request_body
    assert b"101.1-1" in request_body


def test_post_hpc_upload_ingestion_request_handles_http_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    request = urllib.request.Request("http://example.com")
    error = _FakeHttpError(
        request.full_url,
        503,
        "Service Unavailable",
        b"retry later",
    )

    monkeypatch.setattr(
        upload_ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(IngestionRequestError) as exc_info:
        _post_hpc_upload_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-hpc-upload",
            "token",
            str(case_dir),
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.transient is True


def test_post_hpc_upload_ingestion_request_handles_url_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    monkeypatch.setattr(
        upload_ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("network down")
        ),
    )

    with pytest.raises(IngestionRequestError, match="URL error: network down"):
        _post_hpc_upload_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-hpc-upload",
            "token",
            str(case_dir),
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


def test_post_hpc_upload_ingestion_request_handles_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    monkeypatch.setattr(
        upload_ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    with pytest.raises(IngestionRequestError, match="Request timed out"):
        _post_hpc_upload_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-hpc-upload",
            "token",
            str(case_dir),
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


def test_run_ingestor_uploads_once_then_second_run_is_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    captured_calls: list[dict[str, str]] = []
    remote_state = _fresh_state()

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_calls.append(
            {
                "endpoint_url": endpoint_url,
                "api_token": api_token,
                "archive_path": archive_path,
                "machine_name": machine_name,
                "processed_execution_ids": ",".join(processed_execution_ids),
                "timeout_seconds": str(timeout_seconds),
            }
        )
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: remote_state,
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token-123",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code_first = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )
    exit_code_second = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code_first == 0
    assert exit_code_second == 0
    assert len(captured_calls) == 1
    assert captured_calls[0] == {
        "endpoint_url": "http://backend:8000/api/v1/ingestions/from-hpc-upload",
        "api_token": "token-123",
        "archive_path": str(case_dir.resolve()),
        "machine_name": "perlmutter",
        "processed_execution_ids": "100.1-1",
        "timeout_seconds": "30",
    }
    assert str(case_dir.resolve()) in remote_state["cases"]


def test_run_ingestor_archive_mode_dedupes_statusless_snapshot_overlap_by_case_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "old_perf"
    first_case = (
        archive_root / "2026-05" / "performance_archive_2026_05_22_08_01_32" / "case_a"
    )
    second_case = (
        archive_root / "2026-06" / "performance_archive_2026_06_01_08_01_32" / "case_a"
    )
    (first_case / "100.1-1").mkdir(parents=True)
    (second_case / "100.1-1").mkdir(parents=True)
    (second_case / "101.1-1").mkdir(parents=True)

    captured_processed_execution_ids: list[list[str]] = []

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_processed_execution_ids.append(processed_execution_ids)
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code == 0
    assert captured_processed_execution_ids == [["100.1-1"], ["101.1-1"]]


def test_run_ingestor_dry_run_does_not_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    post_calls = 0
    discovery_post_calls = 0

    def fake_post_request(*args, **kwargs):
        nonlocal post_calls
        post_calls += 1
        return {"status_code": 201, "body": {"created_count": 1}}

    def fake_discovery_post(*args, **kwargs):
        nonlocal discovery_post_calls
        discovery_post_calls += 1
        return {"status_code": 201, "body": {}}

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
        discovery_post_request_fn=fake_discovery_post,
    )

    assert exit_code == 0
    assert post_calls == 0
    assert discovery_post_calls == 0


def test_run_ingestor_scan_completed_logs_outcome_counters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="staging",
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
    )

    scan_completed = [
        fields for event, fields in logged_events if event == "scan_completed"
    ][0]

    assert exit_code == 0
    assert scan_completed["accepted_execution_ids"] == 1
    assert scan_completed["rejected_existing_execution_ids"] == 0
    assert scan_completed["rejected_incomplete_execution_ids"] == 0
    assert scan_completed["rejected_invalid_execution_ids"] == 0
    assert scan_completed["deferred_execution_ids"] == 0
    assert scan_completed["scan_mode"] == "staging"


def test_run_ingestor_missing_archive_root_returns_failure(
    monkeypatch, tmp_path: Path
) -> None:
    missing_archive_root = tmp_path / "missing-archive"
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=missing_archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "archive_root_missing" for event, _ in logged_events)


def test_run_ingestor_without_token_returns_config_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)


def test_run_ingestor_returns_failure_when_state_fetch_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            IngestionRequestError("boom", status_code=503, transient=True)
        ),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "state_fetch_failed" for event, _ in logged_events)


def test_run_ingestor_retries_transient_upload_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    attempts: list[int] = []
    sleep_calls: list[float] = []
    remote_state = _fresh_state()

    def fake_post_request(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise IngestionRequestError(
                "temporary error",
                status_code=503,
                transient=True,
            )
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: remote_state,
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=3,
        request_timeout_seconds=10,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        post_request_fn=fake_post_request,
    )

    assert exit_code == 0
    assert len(attempts) == 2
    assert sleep_calls == [1]


def test_main_returns_configuration_error_when_config_build_fails(monkeypatch) -> None:
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(
        upload_ingestor_module,
        "_build_config_from_env",
        lambda: (_ for _ in ()).throw(ValueError("bad config")),
    )
    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)

    exit_code = upload_ingestor_module.main()

    assert exit_code == 1
    assert logged_events == [("configuration_error", {"error": "bad config"})]


def test_main_logs_run_started_and_finished(monkeypatch, tmp_path: Path) -> None:
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=tmp_path,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="staging",
    )
    logged_events: list[tuple[str, dict[str, object]]] = []

    def fake_log_event(event: str, fields: dict[str, object] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(
        upload_ingestor_module, "_build_config_from_env", lambda: config
    )
    monkeypatch.setattr(upload_ingestor_module, "_run_ingestor", lambda cfg: 0)
    monkeypatch.setattr(upload_ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        upload_ingestor_module.time,
        "monotonic",
        lambda: 10.0 if not logged_events else 12.5,
    )

    exit_code = upload_ingestor_module.main()

    assert exit_code == 0
    assert logged_events[0][0] == "run_started"
    assert logged_events[-1][0] == "run_finished"
    assert logged_events[0][1]["scan_mode"] == "staging"
    assert logged_events[-1][1]["scan_mode"] == "staging"


def test_module_main_guard_exits_via_system_exit_on_configuration_error(
    monkeypatch,
) -> None:
    script_path = (
        Path(__file__).resolve().parents[3]
        / "app/scripts/ingestion/hpc_upload_archive_ingestor.py"
    )
    monkeypatch.setenv("MAX_ATTEMPTS", "0")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(script_path), run_name="__main__")

    assert exc_info.value.code == 1


def test_hpc_persists_accepted_deferred_execution_before_upload_limit(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    (archive_root / "case_b" / "200.1-1").mkdir(parents=True)
    persisted: list[nersc_ingestor_module.ExecutionDiscoveryResult] = []
    uploads: list[str] = []
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    def persist(*args: Any, results, **kwargs: Any) -> IngestionRequestResponse:
        persisted.extend(results)
        return {"status_code": 201, "body": {}}

    def upload(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        uploads.append(args[2])
        return {"status_code": 201, "body": {}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=1,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: {},
            post_request_fn=upload,
            discovery_post_request_fn=persist,
        )
        == 0
    )
    assert sorted((result.execution_id, result.outcome) for result in persisted) == [
        ("100.1-1", "accepted"),
        ("200.1-1", "accepted"),
    ]
    assert len(uploads) == 1


def test_hpc_rejected_only_case_persists_typed_result_but_not_transient_error(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "101.1-1").mkdir(parents=True)
    (case_dir / "102.1-1").mkdir(parents=True)
    persisted: list[nersc_ingestor_module.ExecutionDiscoveryResult] = []
    uploads: list[str] = []
    logged_events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    monkeypatch.setattr(
        nersc_ingestor_module,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
    )

    def locator(path: str) -> object:
        if path.endswith("100.1-1"):
            raise IncompleteArchiveError([])
        if path.endswith("101.1-1"):
            raise ArchiveValidationError([])
        raise PermissionError("temporary")

    def persist(*args: Any, results, **kwargs: Any) -> IngestionRequestResponse:
        persisted.extend(results)
        return {"status_code": 201, "body": {}}

    def record_upload(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        uploads.append(args[2])
        return {"status_code": 201, "body": {}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=locator,
            post_request_fn=record_upload,
            discovery_post_request_fn=persist,
        )
        == 0
    )
    assert sorted((result.execution_id, result.outcome) for result in persisted) == [
        ("100.1-1", "rejected_incomplete"),
        ("101.1-1", "rejected_invalid"),
    ]
    assert uploads == []
    scan_fields = next(
        fields for event, fields in logged_events if event == "scan_completed"
    )
    assert scan_fields["skipped_transient"] == 1
    assert scan_fields["transient_execution_ids"] == 1


def test_hpc_discovery_persistence_failure_prevents_upload(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    uploads: list[str] = []
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    def fail_persistence(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("unavailable", status_code=503, transient=False)

    def upload(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        uploads.append(args[2])
        return {"status_code": 201, "body": {}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: {},
            post_request_fn=upload,
            discovery_post_request_fn=fail_persistence,
        )
        == 1
    )
    assert uploads == []
