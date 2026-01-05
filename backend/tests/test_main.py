import pytest
from fastapi.testclient import TestClient

from app.api.version import API_BASE
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestApp:
    def test_health_endpoint(self, client):
        response = client.get(f"{API_BASE}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_meta_endpoint(self, client):
        response = client.get(f"{API_BASE}/meta")

        assert response.status_code == 200
        assert response.json() == {
            "version": "v1",
            "status": "internal",
            "breaking_changes": (
                "No breaking changes are currently declared. This field will describe "
                "required upgrade paths when incompatible API versions are introduced."
            ),
            "build": None,
        }

    def test_app_title(self):
        assert app.title == "SimBoard API"
