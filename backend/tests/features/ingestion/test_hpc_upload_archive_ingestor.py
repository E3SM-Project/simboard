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
from types import SimpleNamespace
from typing import Any

import pytest

from app.features.ingestion.parsers import parser as parser_module
from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
    main_parser,
)
from app.scripts.ingestion import archive_client as client_module
from app.scripts.ingestion import archive_discovery as discovery_module
from app.scripts.ingestion import archive_ingestor_core as core_module
from app.scripts.ingestion import archive_workflow as workflow_module
from app.scripts.ingestion import hpc_upload_archive_ingestor as upload_ingestor_module
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _fresh_state,
)
from app.scripts.ingestion.hpc_upload_archive_ingestor import (
    _build_endpoint_url,
    _create_case_archive,
    _post_hpc_upload_ingestion_request,
    _prepared_hpc_case_submission,
    _run_ingestor,
)


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
        client_module,
        "_post_discovery_results_request",
        lambda *args, **kwargs: {"status_code": 201, "body": {}},
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_archive_checkpoints",
        lambda *args, **kwargs: set(),
    )
    monkeypatch.setattr(
        client_module,
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


def test_hpc_runner_does_not_import_nersc_entrypoint() -> None:
    runner_source = Path(upload_ingestor_module.__file__).read_text()

    assert "app.scripts.ingestion.nersc_archive_ingestor" not in runner_source


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


def test_create_case_archive_includes_only_selected_execution_directories(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    selected_execution = case_dir / "100.1-1"
    unselected_execution = case_dir / "101.1-1"
    (selected_execution / "CaseDocs").mkdir(parents=True)
    unselected_execution.mkdir()
    (selected_execution / "CaseDocs" / "env_run.xml.001").write_text("selected")
    (unselected_execution / "env_run.xml.001").write_text("unselected")
    (case_dir / "case-level.txt").write_text("case root remains")

    archive_path = _create_case_archive(
        str(case_dir), tmp_path, selected_execution_ids=["100.1-1"]
    )

    with tarfile.open(archive_path, "r:gz") as tar_file:
        members = tar_file.getnames()

    assert "case_a" in members
    assert "case_a/100.1-1" in members
    assert "case_a/100.1-1/CaseDocs/env_run.xml.001" in members
    assert not any("101.1-1" in member for member in members)
    assert "case_a/case-level.txt" not in members


def test_parser_accepts_delta_archive_with_required_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = tmp_path / "case_a"
    execution_dir = case_dir / "100.1-1"
    casedocs_dir = execution_dir / "CaseDocs"
    casedocs_dir.mkdir(parents=True)
    for filename in (
        "env_case.xml.001.gz",
        "env_build.xml.001.gz",
        "env_run.xml.001.gz",
        "README.case.001.gz",
    ):
        (casedocs_dir / filename).write_text("fixture")
    for filename in ("CaseStatus.001.gz", "e3sm_timing.001", "GIT_DESCRIBE.001.gz"):
        (execution_dir / filename).write_text("fixture")
    (case_dir / "101.1-1").mkdir()

    parsed_values = {
        "case_docs_env_case": {"case_name": "case_a", "machine": "pm"},
        "case_docs_env_build": {"compiler": "gnu"},
        "case_docs_env_run": {"simulation_start_date": "2025-01-01"},
        "readme_case": {},
        "case_status": {"status": "completed"},
        "e3sm_timing": {"execution_id": "100.1-1"},
        "git_describe": {"git_commit_hash": "abc123"},
    }
    for key, value in parsed_values.items():
        monkeypatch.setitem(
            parser_module.FILE_SPECS[key], "parser", lambda _, v=value: v
        )

    archive_path = _create_case_archive(
        str(case_dir), tmp_path, selected_execution_ids=["100.1-1"]
    )
    parsed, skipped = main_parser(archive_path, tmp_path / "extracted")

    assert skipped == 0
    assert [
        (item.case_name, item.execution_id, item.machine, item.compiler)
        for item in parsed
    ] == [("case_a", "100.1-1", "pm", "gnu")]


@pytest.mark.parametrize("succeeds", [True, False])
def test_prepared_hpc_submission_reuses_payload_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    succeeds: bool,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    candidate = IngestionCandidate(
        case_path=str(case_dir),
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="ignored",
    )
    staged_paths: list[Path] = []
    request_bodies: list[bytes] = []
    events: list[tuple[str, dict[str, object]]] = []
    original_create = upload_ingestor_module._create_case_archive

    def capture_create(*args, **kwargs) -> Path:
        archive_path = original_create(*args, **kwargs)
        staged_paths.append(archive_path)
        return archive_path

    def send_request(*args, **kwargs) -> IngestionRequestResponse:
        request_bodies.append(args[2])
        if not succeeds or len(request_bodies) == 1:
            raise IngestionRequestError("temporary", status_code=503, transient=True)
        return {"status_code": 201, "body": {}}

    monkeypatch.setattr(upload_ingestor_module, "_create_case_archive", capture_create)
    monkeypatch.setattr(
        upload_ingestor_module, "_send_hpc_upload_request", send_request
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_log_event",
        lambda event, fields: events.append((event, fields)),
    )

    with _prepared_hpc_case_submission(candidate, "pm") as submit:
        result = client_module._ingest_case_with_retries(
            candidate,
            "http://backend/upload",
            "token",
            "pm",
            max_attempts=2,
            timeout_seconds=10,
            sleep_fn=lambda _: None,
            post_request_fn=submit,
        )
        assert staged_paths[0].exists()

    assert result["ok"] is succeeds
    assert len(request_bodies) == 2
    assert request_bodies[0] == request_bodies[1]
    assert not staged_paths[0].exists()
    assert [list(fields) for event, fields in events if event == "archive_created"] == [
        ["case_path", "selected_execution_count", "archive_bytes", "duration_seconds"]
    ]
    assert [
        list(fields) for event, fields in events if event == "case_upload_attempt"
    ] == [
        ["case_path", "attempt", "archive_bytes", "duration_seconds"],
        ["case_path", "attempt", "archive_bytes", "duration_seconds"],
    ]


def test_create_case_archive_rejects_non_directory(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("payload")

    with pytest.raises(IngestionRequestError, match="Case path is not a directory"):
        _create_case_archive(str(not_a_directory), tmp_path)


@pytest.mark.parametrize(
    ("response_body", "expected_body"),
    [
        (json.dumps({"created_count": 1}), {"created_count": 1}),
        ("", {}),
        ("null", {}),
    ],
)
def test_post_hpc_upload_ingestion_request_preserves_wire_contract(
    tmp_path: Path,
    monkeypatch,
    response_body: str,
    expected_body: dict[str, int],
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "100.1-1" / "metadata.txt").write_text("payload")
    staged_archive = tmp_path / "case-a.tar.gz"
    staged_archive.write_bytes(b"archive-bytes")
    monkeypatch.setattr(
        upload_ingestor_module,
        "_create_case_archive",
        lambda *args: staged_archive,
    )
    monkeypatch.setattr(
        upload_ingestor_module.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="fixed"),
    )
    captured_request: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_request.append(request)
        assert timeout == 12
        return _FakeHttpResponse(201, response_body)

    monkeypatch.setattr(upload_ingestor_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_hpc_upload_ingestion_request(
        "http://backend:8000/api/v1/ingestions/from-hpc-upload",
        "token",
        str(case_dir),
        "pm",
        processed_execution_ids=["100.1-1", "101.1-1"],
        timeout_seconds=12,
    )

    assert response == {"status_code": 201, "body": expected_body}
    request = captured_request[0]
    boundary = "----SimBoardBoundaryfixed"
    assert request.full_url == ("http://backend:8000/api/v1/ingestions/from-hpc-upload")
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == (
        f"multipart/form-data; boundary={boundary}"
    )
    expected_request_body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="machine_name"'
            f"\r\n\r\npm\r\n--{boundary}\r\nContent-Disposition: form-data; "
            f'name="case_path"\r\n\r\n{case_dir}\r\n--{boundary}\r\n'
            'Content-Disposition: form-data; name="processed_execution_ids"'
            f"\r\n\r\n100.1-1\r\n--{boundary}\r\nContent-Disposition: form-data; "
            'name="processed_execution_ids"\r\n\r\n101.1-1\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{staged_archive.name}"\r\nContent-Type: application/gzip\r\n\r\n'
        ).encode("utf-8")
        + b"archive-bytes\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    assert request.data == expected_request_body


def test_post_hpc_upload_ingestion_request_preserves_invalid_json_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    monkeypatch.setattr(
        upload_ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(201, "{invalid"),
    )

    with pytest.raises(json.JSONDecodeError):
        _post_hpc_upload_ingestion_request(
            "http://backend/from-hpc-upload",
            "token",
            str(case_dir),
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)
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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)

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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)

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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)
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


def test_run_ingestor_fetches_archive_checkpoints_before_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    archive_root.mkdir()
    request_order: list[str] = []

    def fetch_checkpoints(*args: Any, **kwargs: Any) -> set[str]:
        request_order.append("checkpoints")
        return set()

    def fetch_state(*args: Any, **kwargs: Any) -> dict[str, Any]:
        request_order.append("state")
        return _fresh_state()

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_archive_checkpoints",
        fetch_checkpoints,
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        fetch_state,
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
        scan_mode="archive",
    )

    assert _run_ingestor(config, metadata_locator=lambda *_: {}) == 0
    assert request_order == ["checkpoints", "state"]


def test_run_ingestor_returns_failure_when_checkpoint_fetch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, object]]] = []
    state_fetches = 0

    def fetch_state(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal state_fetches
        state_fetches += 1
        return _fresh_state()

    monkeypatch.setattr(
        upload_ingestor_module,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_archive_checkpoints",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            IngestionRequestError("boom", status_code=503, transient=True)
        ),
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        fetch_state,
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
        scan_mode="archive",
    )

    assert _run_ingestor(config, metadata_locator=lambda *_: {}) == 1
    assert (
        "archive_checkpoint_fetch_failed",
        {"status_code": 503, "error": "boom"},
    ) in logged_events
    assert state_fetches == 0


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


def test_run_ingestor_continues_after_archive_staging_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    snapshot = archive_root / "2025-01" / "performance_archive_2025_01_01_00_00_00"
    first_case = snapshot / "COMPLETED" / "case_a"
    second_case = snapshot / "COMPLETED" / "case_b"
    (first_case / "100.1-1").mkdir(parents=True)
    (second_case / "200.1-1").mkdir(parents=True)
    network_attempts: list[str] = []
    finalization_calls = 0
    logged_events: list[tuple[str, dict[str, object]]] = []
    original_create_archive = upload_ingestor_module._create_case_archive

    def fail_first_archive(case_path: str, *args: Any, **kwargs: Any) -> Path:
        if case_path == str(first_case.resolve()):
            raise OSError("staging filesystem unavailable")
        return original_create_archive(case_path, *args, **kwargs)

    def send_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        network_attempts.append("attempt")
        return {"status_code": 201, "body": {}}

    def finalize(*args: Any, **kwargs: Any) -> bool:
        nonlocal finalization_calls
        finalization_calls += 1
        return True

    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    monkeypatch.setattr(
        upload_ingestor_module, "_create_case_archive", fail_first_archive
    )
    monkeypatch.setattr(
        upload_ingestor_module, "_send_hpc_upload_request", send_request
    )
    monkeypatch.setattr(
        upload_ingestor_module, "_finalize_archive_checkpoints", finalize
    )
    monkeypatch.setattr(
        upload_ingestor_module,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
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

    assert _run_ingestor(config, metadata_locator=lambda *_: {}) == 1
    assert network_attempts == ["attempt"]
    assert finalization_calls == 1
    assert (
        "case_ingestion_failed",
        {
            "case_path": str(first_case.resolve()),
            "attempts": 0,
            "status_code": None,
            "error": "staging filesystem unavailable",
        },
    ) in logged_events


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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)

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
    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)
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
    persisted: list[core_module.ExecutionDiscoveryResult] = []
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
    persisted: list[core_module.ExecutionDiscoveryResult] = []
    uploads: list[str] = []
    logged_events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        upload_ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    monkeypatch.setattr(
        workflow_module,
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
