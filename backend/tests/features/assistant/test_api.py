from uuid import UUID, uuid4

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


@pytest.fixture
def authenticated_client(client, normal_user_sync):
    def fake_current_user():
        return User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )

    app.dependency_overrides[current_active_user] = fake_current_user
    return client


def _create_case(db: Session, name: str = "assistant_api_case") -> Case:
    case = Case(name=name)
    db.add(case)
    db.flush()
    return case


def _create_simulation(
    db: Session,
    normal_user_sync: dict[str, UUID | str],
    admin_user_sync: dict[str, UUID | str],
    *,
    execution_id: str = "assistant-api-exec-1",
) -> Simulation:
    machine = db.query(Machine).first()
    assert machine is not None

    case = _create_case(db)
    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference=execution_id,
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
    )
    db.add(ingestion)
    db.flush()

    simulation = Simulation(
        case_id=case.id,
        execution_id=execution_id,
        compset="AQUAPLANET",
        compset_alias="QPC4",
        grid_name="f19_f19",
        grid_resolution="1.9x2.5",
        simulation_type="experimental",
        status="completed",
        initialization_type="startup",
        machine_id=machine.id,
        simulation_start_date="2023-01-01T00:00:00Z",
        git_tag="v2.0.0",
        created_by=normal_user_sync["id"],
        last_updated_by=admin_user_sync["id"],
        ingestion_id=ingestion.id,
    )
    db.add(simulation)
    db.flush()
    case.reference_simulation_id = simulation.id
    db.commit()
    db.refresh(simulation)
    return simulation


class TestSummarizeSimulationEndpoint:
    def test_authenticated_request_returns_summary_contract(
        self, authenticated_client, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(db, normal_user_sync, admin_user_sync)

        response = authenticated_client.post(
            f"{API_BASE}/simulations/{simulation.id}/summary"
        )

        assert response.status_code == 200
        data = response.json()
        assert (
            "Simulation assistant-api-exec-1 belongs to case assistant_api_case."
            in data["answer"]
        )
        assert isinstance(data["citations"], list)
        assert data["assumptions"] == []
        assert isinstance(data["caveats"], list)
        assert data["limitations"] == [
            "This v1 summary uses only metadata already stored in SimBoard. It does not use retrieval, diagnostics interpretation, or LLM reasoning."
        ]
        assert isinstance(data["suggestedFollowups"], list)
        assert UUID(data["traceId"])
        assert {citation["path"] for citation in data["citations"]} >= {
            "simulation.execution_id",
            "case.name",
        }

    def test_unauthenticated_request_returns_401(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(db, normal_user_sync, admin_user_sync)

        response = client.post(f"{API_BASE}/simulations/{simulation.id}/summary")

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    def test_unknown_simulation_returns_404(self, authenticated_client) -> None:
        response = authenticated_client.post(
            f"{API_BASE}/simulations/{uuid4()}/summary"
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Simulation not found"}
