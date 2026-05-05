import json
import urllib.error
import urllib.request
from email.message import Message
from urllib.parse import urlparse

import pytest

from app.api.version import API_BASE
from app.features.pace import api as pace_api


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


class TestResolvePaceExecution:
    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        pace_api._PACE_CACHE.clear()

    def test_endpoint_returns_experiment_id_on_success(
        self, client, monkeypatch
    ) -> None:
        captured_request: list[urllib.request.Request] = []
        execution_id = "52448807.260505-035011"

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            captured_request.append(request)
            assert timeout == 5.0
            return _FakeHttpResponse(200, json.dumps([{"expid": "228920"}]))

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": execution_id}
        )

        assert response.status_code == 200
        assert response.json() == {
            "executionId": execution_id,
            "experimentId": "228920",
        }
        assert captured_request[0].full_url == (
            "https://pace.ornl.gov/ajax/specificSearch/lid:52448807.260505-035011/expid"
        )

    def test_endpoint_returns_experiment_id_on_direct_numeric_payload(
        self, client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _FakeHttpResponse(200, "214043"),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": "214043"}

    def test_endpoint_encodes_only_execution_id_portion(
        self, client, monkeypatch
    ) -> None:
        captured_request: list[urllib.request.Request] = []
        execution_id = "lid/ 42?next=1"

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            captured_request.append(request)
            return _FakeHttpResponse(200, json.dumps([{"expid": "228920"}]))

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": execution_id}
        )

        assert response.status_code == 200
        assert captured_request[0].full_url == (
            "https://pace.ornl.gov/ajax/specificSearch/lid:lid%2F%2042%3Fnext%3D1/expid"
        )

    def test_endpoint_uses_fixed_pace_host(self, client, monkeypatch) -> None:
        captured_request: list[urllib.request.Request] = []
        execution_id = "https://evil.example/path?q=1"

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            captured_request.append(request)
            return _FakeHttpResponse(200, json.dumps([{"expid": "228920"}]))

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": execution_id}
        )

        assert response.status_code == 200
        parsed_url = urlparse(captured_request[0].full_url)
        assert parsed_url.scheme == "https"
        assert parsed_url.netloc == "pace.ornl.gov"
        assert (
            parsed_url.path
            == "/ajax/specificSearch/lid:https%3A%2F%2Fevil.example%2Fpath%3Fq%3D1/expid"
        )

    def test_endpoint_returns_null_on_timeout(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        )

        response = client.get(
            f"{API_BASE}/pace/resolve",
            params={"execution_id": "52448807.260505-035011"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "executionId": "52448807.260505-035011",
            "experimentId": None,
        }

    def test_endpoint_returns_null_on_upstream_non_200(
        self, client, monkeypatch
    ) -> None:
        request = urllib.request.Request(
            "https://pace.ornl.gov/ajax/specificSearch/lid:x/expid"
        )
        error = _FakeHttpError(
            request.full_url, 503, "Service Unavailable", b"retry later"
        )

        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": None}

    def test_endpoint_returns_null_on_malformed_json(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _FakeHttpResponse(200, "{not-json"),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": None}

    def test_endpoint_returns_null_on_empty_array(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _FakeHttpResponse(200, "[]"),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": None}

    def test_endpoint_returns_null_when_expid_is_missing(
        self, client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _FakeHttpResponse(200, json.dumps([{}])),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": None}

    def test_endpoint_returns_null_when_expid_is_blank(
        self, client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            pace_api.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _FakeHttpResponse(
                200, json.dumps([{"expid": "   "}])
            ),
        )

        response = client.get(f"{API_BASE}/pace/resolve", params={"execution_id": "x"})

        assert response.status_code == 200
        assert response.json() == {"executionId": "x", "experimentId": None}

    def test_endpoint_caches_successful_resolutions(self, client, monkeypatch) -> None:
        call_count = 0

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            nonlocal call_count
            call_count += 1
            return _FakeHttpResponse(200, json.dumps([{"expid": "228920"}]))

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        first_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-exec"}
        )
        second_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-exec"}
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_response.json()["experimentId"] == "228920"
        assert second_response.json()["experimentId"] == "228920"
        assert call_count == 1

    def test_endpoint_caches_unresolved_resolutions(self, client, monkeypatch) -> None:
        call_count = 0

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            nonlocal call_count
            call_count += 1
            return _FakeHttpResponse(200, "[]")

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        first_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-miss"}
        )
        second_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-miss"}
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_response.json()["experimentId"] is None
        assert second_response.json()["experimentId"] is None
        assert call_count == 1

    def test_endpoint_caches_timeouts(self, client, monkeypatch) -> None:
        call_count = 0

        def fake_urlopen(request: urllib.request.Request, timeout: float):
            nonlocal call_count
            call_count += 1
            raise TimeoutError()

        monkeypatch.setattr(pace_api.urllib.request, "urlopen", fake_urlopen)

        first_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-timeout"}
        )
        second_response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": "cached-timeout"}
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_response.json()["experimentId"] is None
        assert second_response.json()["experimentId"] is None
        assert call_count == 1

    def test_endpoint_rejects_missing_execution_id(self, client) -> None:
        response = client.get(f"{API_BASE}/pace/resolve")

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["query", "execution_id"]

    @pytest.mark.parametrize("value", ["", "   "])
    def test_endpoint_rejects_blank_execution_id(self, client, value: str) -> None:
        response = client.get(
            f"{API_BASE}/pace/resolve", params={"execution_id": value}
        )

        assert response.status_code == 422
        assert response.json() == {"detail": "execution_id must not be blank"}
