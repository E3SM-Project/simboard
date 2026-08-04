"""Tests for shared archive ingestion HTTP client behavior."""

import json
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path

import pytest

from app.api.version import API_BASE
from app.scripts.ingestion import archive_client as client_module
from app.scripts.ingestion.archive_client import (
    _build_archive_checkpoints_endpoint_url,
    _build_discovery_results_endpoint_url,
    _build_endpoint_url,
    _build_state_endpoint_url,
    _fetch_archive_checkpoints,
    _persist_archive_checkpoints_with_retries,
    _persist_discovery_results_with_retries,
    _post_archive_checkpoints_request,
    _post_discovery_results_request,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_RESULT_BATCH_SIZE,
    ExecutionDiscoveryResult,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
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


def _config(api_base_url: str = "http://backend:8000/") -> IngestorConfig:
    return IngestorConfig(
        api_base_url=api_base_url,
        api_token="token",
        archive_root=Path("/archive"),
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=2,
        request_timeout_seconds=30,
    )


def _raise(error: BaseException) -> None:
    raise error


def test_endpoint_builders_normalize_api_base_url() -> None:
    config = _config()

    assert _build_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/from-path"
    )
    assert _build_state_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/state"
    )
    assert _build_discovery_results_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/discovery-results"
    )
    assert _build_archive_checkpoints_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/archive-checkpoints"
    )
    assert _build_endpoint_url(_config(f"http://backend:8000{API_BASE}")) == (
        "http://backend:8000/api/v1/ingestions/from-path"
    )


def test_post_discovery_results_request_preserves_wire_contract(monkeypatch) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(201, '{"stored_count": 2}')

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_discovery_results_request(
        "http://backend/api/v1/ingestions/discovery-results",
        "token",
        "perlmutter",
        results=[
            ExecutionDiscoveryResult("case-a", "100.1-1", "accepted"),
            ExecutionDiscoveryResult("case-b", "200.1-1", "rejected_invalid"),
        ],
        timeout_seconds=12,
    )

    request, timeout = captured[0]
    assert response == {"status_code": 201, "body": {"stored_count": 2}}
    assert timeout == 12
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == "application/json"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "machine_name": "perlmutter",
        "results": [
            {
                "case_identity": "case-a",
                "execution_id": "100.1-1",
                "outcome": "accepted",
            },
            {
                "case_identity": "case-b",
                "execution_id": "200.1-1",
                "outcome": "rejected_invalid",
            },
        ],
    }


@pytest.mark.parametrize(
    ("error", "match", "status_code"),
    [
        (
            _FakeHttpError("http://backend/discovery-results", 503, "error", b"busy"),
            "HTTP 503: busy",
            503,
        ),
        (urllib.error.URLError("network down"), "URL error: network down", None),
        (TimeoutError(), "Request timed out", None),
    ],
)
def test_post_discovery_results_request_maps_transport_errors(
    monkeypatch,
    error: BaseException,
    match: str,
    status_code: int | None,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _raise(error),
    )

    with pytest.raises(IngestionRequestError, match=match) as exc_info:
        _post_discovery_results_request(
            "http://backend/discovery-results",
            "token",
            "perlmutter",
            results=[],
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.transient is True


def test_post_discovery_results_request_preserves_invalid_json_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(201, "{invalid"),
    )

    with pytest.raises(json.JSONDecodeError):
        _post_discovery_results_request(
            "http://backend/discovery-results",
            "token",
            "perlmutter",
            results=[],
            timeout_seconds=12,
        )


def test_discovery_persistence_batches_results() -> None:
    batch_sizes: list[int] = []

    def persist(
        *args,
        results: list[ExecutionDiscoveryResult],
        **kwargs,
    ) -> IngestionRequestResponse:
        batch_sizes.append(len(results))
        return {"status_code": 201, "body": {}}

    results = [
        ExecutionDiscoveryResult("case-a", str(index), "accepted")
        for index in range(DISCOVERY_RESULT_BATCH_SIZE + 1)
    ]

    assert _persist_discovery_results_with_retries(
        results,
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=1,
        timeout_seconds=12,
        sleep_fn=lambda _: None,
        post_request_fn=persist,
    )
    assert batch_sizes == [DISCOVERY_RESULT_BATCH_SIZE, 1]


def test_fetch_archive_checkpoints_preserves_query_and_sanitizes_response(
    monkeypatch,
) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(
            200,
            json.dumps(
                {
                    "snapshots": [
                        {"archive_month": "2025-01", "snapshot_name": "snap-a"},
                        {"archive_month": "2025-02", "snapshot_name": "snap-b"},
                        {"archive_month": 202503, "snapshot_name": "ignored"},
                    ]
                }
            ),
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

    snapshots = _fetch_archive_checkpoints(
        "http://backend/api/v1/ingestions/archive-checkpoints",
        "token",
        "perlmutter",
        "OLD_PERF",
        archive_start="2025-01",
        archive_end="2025-12",
        timeout_seconds=12,
    )

    request, timeout = captured[0]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
    assert snapshots == {"2025-01/snap-a", "2025-02/snap-b"}
    assert query == {
        "machine_name": ["perlmutter"],
        "archive_name": ["OLD_PERF"],
        "archive_start": ["2025-01"],
        "archive_end": ["2025-12"],
    }
    assert timeout == 12
    assert request.method == "GET"
    assert request.headers["Authorization"] == "Bearer token"


@pytest.mark.parametrize(
    ("error", "match", "status_code"),
    [
        (
            _FakeHttpError("http://backend/checkpoints", 503, "error", b"busy"),
            "HTTP 503: busy",
            503,
        ),
        (urllib.error.URLError("network down"), "Checkpoint request failed:", None),
        (TimeoutError(), "Checkpoint request failed:", None),
    ],
)
def test_fetch_archive_checkpoints_maps_transport_errors(
    monkeypatch,
    error: BaseException,
    match: str,
    status_code: int | None,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _raise(error),
    )

    with pytest.raises(IngestionRequestError, match=match) as exc_info:
        _fetch_archive_checkpoints(
            "http://backend/checkpoints",
            "token",
            "perlmutter",
            "OLD_PERF",
            archive_start=None,
            archive_end=None,
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.transient is True


def test_fetch_archive_checkpoints_maps_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(200, "{invalid"),
    )

    with pytest.raises(IngestionRequestError, match="Invalid checkpoint response:"):
        _fetch_archive_checkpoints(
            "http://backend/checkpoints",
            "token",
            "perlmutter",
            "OLD_PERF",
            archive_start=None,
            archive_end=None,
            timeout_seconds=12,
        )


def test_archive_checkpoint_persistence_retries_and_sorts_keys() -> None:
    attempts: list[list[str]] = []
    sleeps: list[float] = []

    def persist(
        *args,
        snapshot_keys: list[str],
        **kwargs,
    ) -> IngestionRequestResponse:
        attempts.append(snapshot_keys)
        if len(attempts) == 1:
            raise IngestionRequestError("temporary", status_code=503, transient=True)
        return {"status_code": 201, "body": {}}

    assert _persist_archive_checkpoints_with_retries(
        {"2025-02/snap-b", "2025-01/snap-a"},
        "http://backend/checkpoints",
        "token",
        "perlmutter",
        "OLD_PERF",
        max_attempts=2,
        timeout_seconds=12,
        sleep_fn=sleeps.append,
        post_request_fn=persist,
    )
    assert attempts == [
        ["2025-01/snap-a", "2025-02/snap-b"],
        ["2025-01/snap-a", "2025-02/snap-b"],
    ]
    assert sleeps == [1]


def test_archive_checkpoint_persistence_skips_empty_set() -> None:
    def unexpected_request(*args, **kwargs) -> IngestionRequestResponse:
        raise AssertionError("empty checkpoint set must not be persisted")

    assert _persist_archive_checkpoints_with_retries(
        set(),
        "http://backend/checkpoints",
        "token",
        "perlmutter",
        "OLD_PERF",
        max_attempts=2,
        timeout_seconds=12,
        sleep_fn=lambda _: None,
        post_request_fn=unexpected_request,
    )


def test_post_archive_checkpoints_request_preserves_wire_contract(monkeypatch) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(201, '{"stored_count": 2}')

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_archive_checkpoints_request(
        "http://backend/checkpoints",
        "token",
        "perlmutter",
        archive_name="OLD_PERF",
        snapshot_keys=["2025-01/snap-a", "2025-02/snap-b"],
        timeout_seconds=12,
    )

    request, timeout = captured[0]
    assert response == {"status_code": 201, "body": {"stored_count": 2}}
    assert timeout == 12
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == "application/json"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "machine_name": "perlmutter",
        "archive_name": "OLD_PERF",
        "snapshots": [
            {"archive_month": "2025-01", "snapshot_name": "snap-a"},
            {"archive_month": "2025-02", "snapshot_name": "snap-b"},
        ],
    }


@pytest.mark.parametrize(
    ("error", "match", "status_code"),
    [
        (
            _FakeHttpError("http://backend/checkpoints", 503, "error", b"busy"),
            "HTTP 503: busy",
            503,
        ),
        (urllib.error.URLError("network down"), "Checkpoint request failed:", None),
        (TimeoutError(), "Checkpoint request failed:", None),
    ],
)
def test_post_archive_checkpoints_request_maps_transport_errors(
    monkeypatch,
    error: BaseException,
    match: str,
    status_code: int | None,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _raise(error),
    )

    with pytest.raises(IngestionRequestError, match=match) as exc_info:
        _post_archive_checkpoints_request(
            "http://backend/checkpoints",
            "token",
            "perlmutter",
            archive_name="OLD_PERF",
            snapshot_keys=["2025-01/snap-a"],
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.transient is True


def test_post_archive_checkpoints_request_preserves_invalid_json_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(201, "{invalid"),
    )

    with pytest.raises(json.JSONDecodeError):
        _post_archive_checkpoints_request(
            "http://backend/checkpoints",
            "token",
            "perlmutter",
            archive_name="OLD_PERF",
            snapshot_keys=["2025-01/snap-a"],
            timeout_seconds=12,
        )
