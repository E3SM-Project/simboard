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
    _fetch_ingestion_state,
    _ingest_case_with_retries,
    _normalize_remote_state,
    _persist_archive_checkpoints_with_retries,
    _persist_discovery_results_with_retries,
    _post_archive_checkpoints_request,
    _post_discovery_results_request,
    _post_ingestion_request,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_RESULT_BATCH_SIZE,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _case_state_processed_ids,
    _is_transient_status,
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


@pytest.mark.parametrize(("attempt", "expected"), [(1, 1), (2, 2), (3, 4)])
def test_retry_backoff_seconds(attempt: int, expected: int) -> None:
    assert client_module._retry_backoff_seconds(attempt) == expected


@pytest.mark.parametrize(
    ("response_body", "expected_body"),
    [('{"stored_count": 2}', {"stored_count": 2}), ("", {}), ("[]", {})],
)
def test_post_discovery_results_request_preserves_wire_contract(
    monkeypatch,
    response_body: str,
    expected_body: dict[str, int],
) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(201, response_body)

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
    assert response == {"status_code": 201, "body": expected_body}
    assert timeout == 12
    assert request.full_url == ("http://backend/api/v1/ingestions/discovery-results")
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == "application/json"
    assert isinstance(request.data, bytes)
    expected_payload = {
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
    assert request.data == json.dumps(expected_payload).encode("utf-8")


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


def test_archive_checkpoint_persistence_retries_and_sorts_keys(monkeypatch) -> None:
    attempts: list[list[str]] = []
    sleeps: list[float] = []
    logged_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        client_module,
        "_log_event",
        lambda event, fields: logged_events.append((event, fields)),
    )

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
    assert logged_events == [
        (
            "archive_checkpoint_persistence_failed",
            {
                "attempt": 1,
                "status_code": 503,
                "retrying": True,
                "error": "temporary",
            },
        )
    ]


def test_ingest_case_retry_timing_events_have_stable_fields(monkeypatch) -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    events: list[tuple[str, dict[str, object]]] = []
    monotonic_values = iter([10.0, 11.0, 12.25, 13.0, 14.5, 15.75])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        client_module,
        "_log_event",
        lambda event, fields: events.append((event, fields)),
    )
    attempts = 0

    def submit(*args, **kwargs) -> IngestionRequestResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IngestionRequestError("temporary", status_code=503, transient=True)
        return {"status_code": 201, "body": {}}

    result = _ingest_case_with_retries(
        candidate,
        "http://backend/ingestions",
        "token",
        "pm",
        max_attempts=2,
        timeout_seconds=10,
        sleep_fn=lambda _: None,
        post_request_fn=submit,
    )

    assert result["ok"] is True
    assert events[1] == (
        "case_ingestion_attempt_completed",
        {"case_path": candidate.case_path, "attempt": 1, "duration_seconds": 1.25},
    )
    assert events[2] == (
        "case_ingestion_attempt_completed",
        {"case_path": candidate.case_path, "attempt": 2, "duration_seconds": 1.5},
    )
    assert events[3] == (
        "case_ingestion_retry_completed",
        {"case_path": candidate.case_path, "attempts": 2, "duration_seconds": 5.75},
    )


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


@pytest.mark.parametrize(
    ("response_body", "expected_body"),
    [('{"stored_count": 2}', {"stored_count": 2}), ("", {}), ("42", {})],
)
def test_post_archive_checkpoints_request_preserves_wire_contract(
    monkeypatch,
    response_body: str,
    expected_body: dict[str, int],
) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(201, response_body)

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
    assert response == {"status_code": 201, "body": expected_body}
    assert timeout == 12
    assert request.full_url == "http://backend/checkpoints"
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == "application/json"
    assert isinstance(request.data, bytes)
    expected_payload = {
        "machine_name": "perlmutter",
        "archive_name": "OLD_PERF",
        "snapshots": [
            {"archive_month": "2025-01", "snapshot_name": "snap-a"},
            {"archive_month": "2025-02", "snapshot_name": "snap-b"},
        ],
    }
    assert request.data == json.dumps(expected_payload).encode("utf-8")


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


def test_ingest_case_with_retries_retries_transient_errors(monkeypatch) -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    attempts: list[int] = []
    sleep_calls: list[float] = []
    logged_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        client_module,
        "_log_event",
        lambda event, fields: logged_events.append((event, fields)),
    )

    def fake_post_request(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise IngestionRequestError(
                "temporary error",
                status_code=503,
                transient=True,
            )
        return {"status_code": 201, "body": {"created_count": 1, "errors": []}}

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="perlmutter",
        max_attempts=3,
        timeout_seconds=10,
        sleep_fn=sleep_calls.append,
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert sleep_calls == [1]
    assert logged_events[0] == (
        "case_ingestion_request_failed",
        {
            "case_path": "/performance_archive/case_a",
            "attempt": 1,
            "status_code": 503,
            "transient": True,
            "retrying": True,
            "error": "temporary error",
        },
    )
    assert [event for event, _ in logged_events[1:]] == [
        "case_ingestion_attempt_completed",
        "case_ingestion_attempt_completed",
        "case_ingestion_retry_completed",
    ]
    assert [list(fields) for _, fields in logged_events[1:]] == [
        ["case_path", "attempt", "duration_seconds"],
        ["case_path", "attempt", "duration_seconds"],
        ["case_path", "attempts", "duration_seconds"],
    ]


def test_ingest_case_with_retries_does_not_retry_non_transient_errors() -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    call_count = 0

    def fake_post_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise IngestionRequestError(
            "bad request",
            status_code=400,
            transient=False,
        )

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="perlmutter",
        max_attempts=3,
        timeout_seconds=10,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is False
    assert result["attempts"] == 1
    assert call_count == 1


def test_ingest_case_with_retries_uses_default_post_request_fn(monkeypatch) -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    captured: list[tuple[str, str, str, str, str, int]] = []

    def fake_post(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured.append(
            (
                endpoint_url,
                api_token,
                archive_path,
                machine_name,
                ",".join(processed_execution_ids),
                timeout_seconds,
            )
        )
        return {"status_code": 201, "body": {"created_count": 1}}

    monkeypatch.setattr(client_module, "_post_ingestion_request", fake_post)

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=1,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
    )

    assert result["ok"] is True
    assert captured == [
        (
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/performance_archive/case_a",
            "pm",
            "100.1-1",
            5,
        )
    ]


def test_ingest_case_with_retries_normalizes_non_dict_body() -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )

    def fake_post_request(*args, **kwargs) -> IngestionRequestResponse:
        return {"status_code": 201, "body": "bad"}  # type: ignore[typeddict-item]

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=1,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is True
    assert result["body"] == {}


def test_ingest_case_with_retries_returns_exhausted_retries_when_zero_attempts() -> (
    None
):
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )

    def fake_post_request(*args, **kwargs) -> IngestionRequestResponse:
        return {"status_code": 201, "body": {}}

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=0,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result == {
        "ok": False,
        "attempts": 0,
        "status_code": None,
        "body": None,
        "error": "Exhausted retries",
    }


@pytest.mark.parametrize(
    ("response_body", "expected_body"),
    [
        (json.dumps({"created_count": 1}), {"created_count": 1}),
        ("", {}),
        ('"unexpected"', {}),
    ],
)
def test_post_ingestion_request_preserves_wire_contract(
    monkeypatch,
    response_body: str,
    expected_body: dict[str, int],
) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(201, response_body)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_ingestion_request(
        "http://backend:8000/api/v1/ingestions/from-path",
        "token",
        "/archive/case_a",
        "pm",
        processed_execution_ids=["100.1-1", "101.1-1"],
        timeout_seconds=12,
    )

    request, timeout = captured[0]
    assert response == {"status_code": 201, "body": expected_body}
    assert timeout == 12
    assert request.full_url == ("http://backend:8000/api/v1/ingestions/from-path")
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Content-type"] == "application/json"
    assert isinstance(request.data, bytes)
    expected_payload = {
        "archive_path": "/archive/case_a",
        "machine_name": "pm",
        "processed_execution_ids": ["100.1-1", "101.1-1"],
    }
    assert request.data == json.dumps(expected_payload).encode("utf-8")


@pytest.mark.parametrize(
    ("error", "match", "status_code"),
    [
        (
            _FakeHttpError("http://backend/from-path", 503, "error", b"busy"),
            "HTTP 503: busy",
            503,
        ),
        (urllib.error.URLError("network down"), "URL error: network down", None),
        (TimeoutError(), "Request timed out", None),
    ],
)
def test_post_ingestion_request_maps_transport_errors(
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
        _post_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/archive/case_a",
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.transient is True


def test_post_ingestion_request_preserves_invalid_json_error(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(201, "{invalid"),
    )

    with pytest.raises(json.JSONDecodeError):
        _post_ingestion_request(
            "http://backend/from-path",
            "token",
            "/archive/case_a",
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


def test_is_transient_status() -> None:
    assert _is_transient_status(503) is True
    assert _is_transient_status(400) is False


def test_normalize_remote_state_rejects_non_dict_payload() -> None:
    with pytest.raises(
        IngestionRequestError,
        match="Invalid ingestion state response payload.",
    ):
        _normalize_remote_state([])


def test_normalize_remote_state_sanitizes_cases() -> None:
    state = _normalize_remote_state(
        {
            "cases": {
                "/archive/case_a": {
                    "processed_execution_ids": ["101.1-1", "100.1-1", "100.1-1"],
                },
                "/archive/case_b": {"processed_execution_ids": "bad"},
                123: {"processed_execution_ids": ["skip"]},
            }
        }
    )

    assert state["cases"]["/archive/case_a"]["processed_execution_ids"] == [
        "100.1-1",
        "101.1-1",
    ]
    assert state["cases"]["/archive/case_b"]["processed_execution_ids"] == []
    assert "/archive/case_a" in state["cases"]
    assert 123 not in state["cases"]


def test_normalize_remote_state_replaces_non_dict_cases_root() -> None:
    state = _normalize_remote_state({"cases": []})

    assert state["cases"] == {}


def test_case_state_processed_ids_ignores_non_list() -> None:
    assert _case_state_processed_ids({"processed_execution_ids": "bad"}) == set()


@pytest.mark.parametrize(
    ("response_body", "expected_execution_ids"),
    [
        (
            json.dumps(
                {
                    "machine_name": "pm",
                    "cases": {
                        "/archive/case_a": {
                            "processed_execution_ids": ["100.1-1"],
                            "fingerprint": "fp-1",
                        }
                    },
                }
            ),
            ["100.1-1"],
        ),
        ("", None),
    ],
)
def test_fetch_ingestion_state_preserves_wire_contract(
    monkeypatch,
    response_body: str,
    expected_execution_ids: list[str] | None,
) -> None:
    captured: list[tuple[urllib.request.Request, int]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured.append((request, timeout))
        return _FakeHttpResponse(200, response_body)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

    state = _fetch_ingestion_state(
        "http://backend:8000/api/v1/ingestions/state",
        "token",
        "pm",
        timeout_seconds=12,
    )

    request, timeout = captured[0]
    if expected_execution_ids is None:
        assert state["cases"] == {}
    else:
        assert state["cases"]["/archive/case_a"]["processed_execution_ids"] == (
            expected_execution_ids
        )
    assert timeout == 12
    assert request.method == "GET"
    assert urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query) == {
        "machine_name": ["pm"]
    }
    assert request.headers["Authorization"] == "Bearer token"


@pytest.mark.parametrize(
    ("error", "match", "status_code"),
    [
        (
            _FakeHttpError("http://backend/state", 503, "error", b"busy"),
            "HTTP 503: busy",
            503,
        ),
        (urllib.error.URLError("network down"), "URL error: network down", None),
        (TimeoutError(), "Request timed out", None),
    ],
)
def test_fetch_ingestion_state_maps_transport_errors(
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
        _fetch_ingestion_state(
            "http://backend/state",
            "token",
            "pm",
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.transient is True


def test_fetch_ingestion_state_wraps_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(200, "{invalid"),
    )

    with pytest.raises(IngestionRequestError, match="Invalid JSON response:"):
        _fetch_ingestion_state(
            "http://backend/state",
            "token",
            "pm",
            timeout_seconds=12,
        )


@pytest.mark.parametrize("payload", [[], {}, {"snapshots": "bad"}])
def test_fetch_archive_checkpoints_rejects_invalid_payload(
    monkeypatch,
    payload: object,
) -> None:
    monkeypatch.setattr(
        client_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(200, json.dumps(payload)),
    )

    with pytest.raises(
        IngestionRequestError,
        match="Invalid checkpoint response payload.",
    ) as exc_info:
        _fetch_archive_checkpoints(
            "http://backend/checkpoints",
            "token",
            "pm",
            "OLD_PERF",
            archive_start=None,
            archive_end=None,
            timeout_seconds=12,
        )

    assert exc_info.value.transient is False


def test_discovery_persistence_retries_transient_failure(monkeypatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []
    logged_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        client_module,
        "_log_event",
        lambda event, fields: logged_events.append((event, fields)),
    )

    def persist(*args, **kwargs) -> IngestionRequestResponse:
        attempts.append(1)
        if len(attempts) == 1:
            raise IngestionRequestError("temporary", status_code=503, transient=True)
        return {"status_code": 201, "body": {}}

    ok = _persist_discovery_results_with_retries(
        [ExecutionDiscoveryResult("case_a", "100.1-1", "accepted")],
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=2,
        timeout_seconds=30,
        sleep_fn=sleeps.append,
        post_request_fn=persist,
    )

    assert ok is True
    assert len(attempts) == 2
    assert sleeps == [1]
    assert logged_events == [
        (
            "discovery_results_persistence_failed",
            {
                "attempt": 1,
                "status_code": 503,
                "transient": True,
                "retrying": True,
                "error": "temporary",
            },
        )
    ]


def test_discovery_persistence_stops_on_terminal_failure(monkeypatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []
    logged_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        client_module,
        "_log_event",
        lambda event, fields: logged_events.append((event, fields)),
    )

    def persist(*args, **kwargs) -> IngestionRequestResponse:
        attempts.append(1)
        raise IngestionRequestError("invalid", status_code=400, transient=False)

    ok = _persist_discovery_results_with_retries(
        [ExecutionDiscoveryResult("case_a", "100.1-1", "accepted")],
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=3,
        timeout_seconds=30,
        sleep_fn=sleeps.append,
        post_request_fn=persist,
    )

    assert ok is False
    assert len(attempts) == 1
    assert sleeps == []
    assert logged_events == [
        (
            "discovery_results_persistence_failed",
            {
                "attempt": 1,
                "status_code": 400,
                "transient": False,
                "retrying": False,
                "error": "invalid",
            },
        )
    ]


def test_discovery_persistence_skips_empty_results() -> None:
    def unexpected_request(*args, **kwargs) -> IngestionRequestResponse:
        raise AssertionError("empty discovery results must not be persisted")

    assert _persist_discovery_results_with_retries(
        [],
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=3,
        timeout_seconds=30,
        sleep_fn=lambda _: None,
        post_request_fn=unexpected_request,
    )


def test_discovery_persistence_deduplicates_snapshot_outcomes_by_precedence() -> None:
    persisted: list[ExecutionDiscoveryResult] = []

    def persist(
        *args,
        results: list[ExecutionDiscoveryResult],
        **kwargs,
    ) -> IngestionRequestResponse:
        persisted.extend(results)
        return {"status_code": 201, "body": {}}

    result = _persist_discovery_results_with_retries(
        [
            ExecutionDiscoveryResult("case_a", "100.1-1", "rejected_incomplete"),
            ExecutionDiscoveryResult("case_a", "100.1-1", "rejected_invalid"),
            ExecutionDiscoveryResult("case_a", "100.1-1", "accepted"),
            ExecutionDiscoveryResult("case_a", "100.1-1", "rejected_incomplete"),
            ExecutionDiscoveryResult("case_b", "200.1-1", "rejected_invalid"),
            ExecutionDiscoveryResult("case_b", "200.1-1", "rejected_incomplete"),
        ],
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=1,
        timeout_seconds=30,
        sleep_fn=lambda _: None,
        post_request_fn=persist,
    )

    assert result is True
    assert [
        (item.case_identity, item.execution_id, item.outcome) for item in persisted
    ] == [
        ("case_a", "100.1-1", "accepted"),
        ("case_b", "200.1-1", "rejected_invalid"),
    ]
