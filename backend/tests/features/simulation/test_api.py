from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.models import Case, Simulation
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


def _create_case(db: Session, name: str = "test_case") -> Case:
    """Helper to create a Case."""
    case = Case(name=name)
    db.add(case)
    db.flush()
    return case


class TestCreateSimulation:
    def test_endpoint_succeeds_with_valid_payload(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_create")
        db.commit()

        payload = {
            "caseId": str(case.id),
            "executionId": "1081156.251218-200923",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "experimental",
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

        res = client.post(f"{API_BASE}/simulations", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["caseId"] == str(case.id)
        assert data["caseName"] == "test_case_create"
        assert data["executionId"] == "1081156.251218-200923"
        assert data["createdBy"] == str(normal_user_sync["id"])
        assert data["lastUpdatedBy"] == str(normal_user_sync["id"])
        assert len(data["artifacts"]) == 1
        assert len(data["links"]) == 1


class TestListSimulations:
    def test_endpoint_returns_empty_list(self, client):
        res = client.get(f"{API_BASE}/simulations")
        assert res.status_code == 200
        assert res.json() == []

    def test_endpoint_returns_simulations_with_data(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        case = _create_case(db, "test_case_list")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_simulation_list",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="list-test-exec-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        res = client.get(f"{API_BASE}/simulations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["caseName"] == "test_case_list"
        assert data[0]["executionId"] == "list-test-exec-1"


class TestGetSimulation:
    def test_endpoint_succeeds_with_valid_id(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        case = _create_case(db, "test_case_get")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_simulation_get",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="get-test-exec-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        res = client.get(f"{API_BASE}/simulations/{sim.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["caseName"] == "test_case_get"
        assert data["executionId"] == "get-test-exec-1"

    def test_endpoint_raises_404_if_simulation_not_found(self, client):
        res = client.get(f"{API_BASE}/simulations/{uuid4()}")
        assert res.status_code == 404
        assert res.json() == {"detail": "Simulation not found"}
