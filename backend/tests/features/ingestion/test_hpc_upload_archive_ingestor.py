"""Tests for automated HPC upload archive ingestor runner."""

import json
import tarfile
import urllib.request
from pathlib import Path

from app.scripts.ingestion import hpc_upload_archive_ingestor as upload_ingestor_module
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
    assert b'name="processed_execution_ids[]"' in request_body
    assert b"100.1-1" in request_body
    assert b"101.1-1" in request_body


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


def test_run_ingestor_dry_run_does_not_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    post_calls = 0

    def fake_post_request(*args, **kwargs):
        nonlocal post_calls
        post_calls += 1
        return {"status_code": 201, "body": {"created_count": 1}}

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
    )

    assert exit_code == 0
    assert post_calls == 0


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
