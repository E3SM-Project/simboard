from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.machine.models import Machine
from app.features.simulation.schemas import SimulationCreate
from app.features.upload.schemas import IngestArchiveRequest, IngestArchiveResponse
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app


@pytest.fixture(autouse=True)
def override_auth_dependency(normal_user_sync):
    """Auto-login a test user for endpoints requiring authentication."""

    def fake_current_user():
        return User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )

    app.dependency_overrides[current_active_user] = fake_current_user

    yield
    app.dependency_overrides.clear()


class TestIngestArchiveSchemas:
    def test_request_schema_serialization(self):
        payload = {
            "archive_path": "/tmp/archive.tar.gz",
            "output_dir": "/tmp/output",
        }

        request = IngestArchiveRequest(**payload)
        assert request.model_dump() == payload

    def test_response_schema_serialization(self):
        payload = {
            "created_count": 1,
            "duplicate_count": 0,
            "simulations": [],
        }

        response = IngestArchiveResponse(**payload)
        assert response.model_dump() == payload


class TestIngestArchiveEndpoint:
    def test_endpoint_returns_summary(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        payload = {
            "archive_path": "/tmp/archive.tar.gz",
            "output_dir": "/tmp/output",
        }

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.upload.api.ingest_archive",
            return_value=(mock_simulations, 1, 0),
        ):
            res = client.post(f"{API_BASE}/upload/ingest", json=payload)

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0
        assert data["simulations"][0]["name"] == "Test Simulation"

    def test_endpoint_returns_409_on_conflict(self, client):
        payload = {
            "archive_path": "/tmp/archive.tar.gz",
            "output_dir": "/tmp/output",
        }

        with patch(
            "app.features.upload.api.ingest_archive",
            side_effect=ValueError("Duplicate simulation"),
        ):
            res = client.post(f"{API_BASE}/upload/ingest", json=payload)

        assert res.status_code == 409
        assert res.json()["detail"] == "Duplicate simulation"
