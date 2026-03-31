from contextlib import nullcontext
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.api import create_simulation
from app.features.simulation.models import Case, Simulation
from app.features.simulation.schemas import SimulationCreate
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


class TestListCases:
    def test_endpoint_returns_empty_list(self, client):
        res = client.get(f"{API_BASE}/cases")
        assert res.status_code == 200
        assert res.json() == []

    def test_endpoint_returns_cases_with_nested_simulations(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_nested")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_case_nested",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=2,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        # Create two simulations under the same case
        sim1 = Simulation(
            case_id=case.id,
            execution_id="case-nested-exec-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        sim2 = Simulation(
            case_id=case.id,
            execution_id="case-nested-exec-2",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-02-01T00:00:00Z",
            run_config_deltas={
                "compiler": {"canonical": "gcc-11", "current": "gcc-12"}
            },
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim1)
        db.flush()
        # Set canonical
        assert sim1.id is not None
        case.canonical_simulation_id = sim1.id
        db.add(sim2)
        db.commit()

        res = client.get(f"{API_BASE}/cases")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1

        case_data = data[0]
        assert case_data["name"] == "test_case_nested"
        assert case_data["canonicalSimulationId"] == str(sim1.id)
        assert case_data["machineNames"] == [machine.name]
        assert case_data["hpcUsernames"] == []

        # Verify nested simulations are SimulationSummaryOut (lightweight)
        sims = case_data["simulations"]
        assert len(sims) == 2

        # Each summary should have only lightweight fields
        for s in sims:
            assert "id" in s
            assert "executionId" in s
            assert "status" in s
            assert "isCanonical" in s
            assert "changeCount" in s
            assert "simulationStartDate" in s
            # Must NOT include heavy fields
            assert "machine" not in s
            assert "artifacts" not in s
            assert "links" not in s
            assert "groupedArtifacts" not in s
            assert "groupedLinks" not in s
            assert "runConfigDeltas" not in s
            assert "createdByUser" not in s

        # Verify canonical and change_count derivation
        exec_ids = {s["executionId"]: s for s in sims}
        assert exec_ids["case-nested-exec-1"]["isCanonical"] is True
        assert exec_ids["case-nested-exec-1"]["changeCount"] == 0
        assert exec_ids["case-nested-exec-2"]["isCanonical"] is False
        assert exec_ids["case-nested-exec-2"]["changeCount"] == 1


class TestListCaseNames:
    def test_endpoint_returns_empty_list(self, client):
        res = client.get(f"{API_BASE}/cases/names")
        assert res.status_code == 200
        assert res.json() == []

    def test_endpoint_returns_case_names_sorted_alphabetically(
        self, client, db: Session
    ):
        _create_case(db, "zeta_case")
        _create_case(db, "alpha_case")
        _create_case(db, "beta_case")
        db.commit()

        res = client.get(f"{API_BASE}/cases/names")
        assert res.status_code == 200
        assert res.json() == ["alpha_case", "beta_case", "zeta_case"]


class TestGetCase:
    def test_endpoint_returns_case_with_simulations(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_detail")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_case_detail",
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
            execution_id="case-detail-exec-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.flush()
        assert sim.id is not None
        case.canonical_simulation_id = sim.id
        db.commit()

        res = client.get(f"{API_BASE}/cases/{case.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "test_case_detail"
        assert len(data["simulations"]) == 1
        assert data["machineNames"] == [machine.name]
        assert data["hpcUsernames"] == []
        assert data["simulations"][0]["executionId"] == "case-detail-exec-1"
        assert data["simulations"][0]["isCanonical"] is True

    def test_endpoint_raises_404_if_case_not_found(self, client):
        res = client.get(f"{API_BASE}/cases/{uuid4()}")
        assert res.status_code == 404
        assert res.json() == {"detail": "Case not found"}


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

    def test_endpoint_returns_400_when_case_not_found(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        payload = {
            "caseId": str(uuid4()),
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
        }

        res = client.post(f"{API_BASE}/simulations", json=payload)
        assert res.status_code == 400
        assert "not found" in res.json()["detail"].lower()

    def test_first_manual_create_sets_canonical_on_case(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_first_manual_canonical")
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
        }

        res = client.post(f"{API_BASE}/simulations", json=payload)
        assert res.status_code == 201
        data = res.json()

        assert data["isCanonical"] is True
        assert data["runConfigDeltas"] is None

        db.refresh(case)
        assert case.canonical_simulation_id is not None
        assert str(case.canonical_simulation_id) == data["id"]

    def test_create_simulation_raises_500_when_reload_fails(self) -> None:
        case_id = uuid4()
        machine_id = uuid4()
        user_id = uuid4()

        payload = SimulationCreate.model_validate(
            {
                "caseId": str(case_id),
                "executionId": "reload-missing-exec-1",
                "compset": "AQUAPLANET",
                "compsetAlias": "QPC4",
                "gridName": "f19_f19",
                "gridResolution": "1.9x2.5",
                "initializationType": "startup",
                "simulationType": "experimental",
                "status": "created",
                "machineId": str(machine_id),
                "simulationStartDate": "2023-01-01T00:00:00Z",
            }
        )

        user = User(
            id=user_id,
            email="reload-fail@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )

        case = Case(id=case_id, name="reload_fail_case")

        db = MagicMock(spec=Session)
        case_query = MagicMock()
        case_query.filter.return_value.first.return_value = case

        sim_query = MagicMock()
        sim_query.options.return_value.filter.return_value.one_or_none.return_value = (
            None
        )

        db.query.side_effect = [case_query, sim_query]

        with patch(
            "app.features.simulation.api.transaction", return_value=nullcontext()
        ):
            with pytest.raises(HTTPException) as exc_info:
                create_simulation(payload=payload, db=db, user=user)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to load newly created simulation."


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

    def test_filter_by_case_name(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case_a = _create_case(db, "case_alpha")
        case_b = _create_case(db, "case_beta")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_filter_case_name",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=2,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        for case, exec_id in [(case_a, "exec-a"), (case_b, "exec-b")]:
            db.add(
                Simulation(
                    case_id=case.id,
                    execution_id=exec_id,
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    initialization_type="startup",
                    simulation_type="experimental",
                    status="created",
                    machine_id=machine.id,
                    simulation_start_date="2023-01-01T00:00:00Z",
                    created_by=normal_user_sync["id"],
                    last_updated_by=admin_user_sync["id"],
                    ingestion_id=ingestion.id,
                )
            )
        db.commit()

        # No filter returns both
        res = client.get(f"{API_BASE}/simulations")
        assert res.status_code == 200
        assert len(res.json()) == 2

        # Filter by case_name=case_alpha returns only one
        res = client.get(f"{API_BASE}/simulations", params={"case_name": "case_alpha"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["caseName"] == "case_alpha"

        # Non-matching filter returns empty
        res = client.get(f"{API_BASE}/simulations", params={"case_name": "nonexistent"})
        assert res.status_code == 200
        assert len(res.json()) == 0

    def test_filter_by_case_group(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case_g1 = Case(name="case_group1", case_group="ensemble_A")
        case_g2 = Case(name="case_group2", case_group="ensemble_B")
        db.add_all([case_g1, case_g2])
        db.flush()

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_filter_case_group",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=2,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        for case, exec_id in [(case_g1, "exec-g1"), (case_g2, "exec-g2")]:
            db.add(
                Simulation(
                    case_id=case.id,
                    execution_id=exec_id,
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    initialization_type="startup",
                    simulation_type="experimental",
                    status="created",
                    machine_id=machine.id,
                    simulation_start_date="2023-01-01T00:00:00Z",
                    created_by=normal_user_sync["id"],
                    last_updated_by=admin_user_sync["id"],
                    ingestion_id=ingestion.id,
                )
            )
        db.commit()

        res = client.get(f"{API_BASE}/simulations", params={"case_group": "ensemble_A"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["caseGroup"] == "ensemble_A"

    def test_filter_by_case_name_and_case_group(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = Case(name="combo_case", case_group="combo_group")
        case_other = Case(name="other_case", case_group="combo_group")
        db.add_all([case, case_other])
        db.flush()

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_filter_combo",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=2,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        for c, exec_id in [(case, "exec-combo"), (case_other, "exec-other")]:
            db.add(
                Simulation(
                    case_id=c.id,
                    execution_id=exec_id,
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    initialization_type="startup",
                    simulation_type="experimental",
                    status="created",
                    machine_id=machine.id,
                    simulation_start_date="2023-01-01T00:00:00Z",
                    created_by=normal_user_sync["id"],
                    last_updated_by=admin_user_sync["id"],
                    ingestion_id=ingestion.id,
                )
            )
        db.commit()

        # Both share same group, but filtering by both narrows to one
        res = client.get(
            f"{API_BASE}/simulations",
            params={"case_name": "combo_case", "case_group": "combo_group"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["caseName"] == "combo_case"
        assert data[0]["caseGroup"] == "combo_group"


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


class TestSimulationBrowserIncludesCaseMetadata:
    def test_simulation_list_includes_case_name_and_id(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        """The flat /simulations endpoint includes case metadata on each row."""
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_browser")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_sim_browser",
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
            execution_id="browser-exec-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.commit()

        res = client.get(f"{API_BASE}/simulations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        # Verify case metadata is present on the flat simulation row
        assert data[0]["caseId"] == str(case.id)
        assert data[0]["caseName"] == "test_case_browser"
        assert data[0]["executionId"] == "browser-exec-1"
