from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.simulation.models import Simulation
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


class TestCreateSimulation:
    def test_endpoint_succeeds_with_valid_payload(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        payload = {
            "name": "Test Simulation 2",
            "caseName": "test_case_2",
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
            "artifacts": [
                {
                    "kind": "output",
                    "uri": "http://example.com/artifact2",
                    "label": "artifact2",
                }
            ],
            "links": [
                {
                    "kind": "diagnostic",
                    "url": "http://example.com/link2",
                    "label": "link2",
                }
            ],
        }

        res = client.post("/simulations", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == payload["name"]
        assert data["createdBy"] == str(normal_user_sync["id"])
        assert data["lastUpdatedBy"] == str(normal_user_sync["id"])
        assert len(data["artifacts"]) == 1
        assert len(data["links"]) == 1


class TestListSimulations:
    def test_endpoint_returns_empty_list(self, client):
        res = client.get("/simulations")
        assert res.status_code == 200
        assert res.json() == []

    def test_endpoint_returns_simulations_with_data(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        sim = Simulation(
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        res = client.get("/simulations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["name"] == sim.name


class TestGetSimulation:
    def test_endpoint_succeeds_with_valid_id(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        sim = Simulation(
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        res = client.get(f"/simulations/{sim.id}")
        assert res.status_code == 200
        assert res.json()["name"] == sim.name

    def test_endpoint_raises_404_if_simulation_not_found(self, client):
        res = client.get(f"/simulations/{uuid4()}")
        assert res.status_code == 404
        assert res.json() == {"detail": "Simulation not found"}
