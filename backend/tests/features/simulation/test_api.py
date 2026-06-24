from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.core.config import settings
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.api import (
    _validate_simulation_case_identity,
    create_simulation,
    update_simulation,
)
from app.features.simulation.enums import SimulationStatus, SimulationType
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation
from app.features.simulation.schemas import SimulationCreate, SimulationUpdate
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
            has_verified_e3sm_membership=True,
        )

    app.dependency_overrides[current_active_user] = fake_current_user

    yield
    app.dependency_overrides.clear()


def _override_current_user(
    *, user_id, email: str, role: UserRole, has_membership: bool
):
    def fake_current_user():
        return User(
            id=user_id,
            email=email,
            is_active=True,
            is_verified=True,
            role=role,
            has_verified_e3sm_membership=has_membership,
        )

    app.dependency_overrides[current_active_user] = fake_current_user


def _create_case(db: Session, name: str = "test_case") -> Case:
    """Helper to create a Case."""
    machine = db.query(Machine).first()
    assert machine is not None

    case = Case(name=name, machine_id=machine.id, hpc_username="test-user")

    db.add(case)
    db.flush()

    return case


def _create_ingestion(
    db: Session,
    machine_id,
    user_id,
    source_reference: str = "test_simulation_ingestion",
) -> Ingestion:
    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference=source_reference,
        machine_id=machine_id,
        triggered_by=user_id,
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
    )
    db.add(ingestion)
    db.flush()

    return ingestion


def _create_simulation_record(
    db: Session,
    *,
    case: Case,
    machine_id,
    ingestion_id,
    created_by,
    last_updated_by,
    execution_id: str = "patch-test-exec-1",
    description: str | None = "Original description",
    updated_at: datetime | None = None,
) -> Simulation:
    sim = Simulation(
        case_id=case.id,
        execution_id=execution_id,
        description=description,
        compset="AQUAPLANET",
        compset_alias="QPC4",
        grid_name="f19_f19",
        grid_resolution="1.9x2.5",
        initialization_type="startup",
        simulation_type="experimental",
        status="created",
        campaign="campaign-original",
        experiment_type="historical",
        machine_id=machine_id,
        simulation_start_date="2023-01-01T00:00:00Z",
        compiler="gcc",
        key_features="Original features",
        known_issues="Original issues",
        notes_markdown="Original notes",
        git_repository_url="https://example.com/original",
        git_branch="main",
        git_tag="v1.0",
        git_commit_hash="abc123",
        hpc_username="old-user",
        created_by=created_by,
        last_updated_by=last_updated_by,
        ingestion_id=ingestion_id,
        updated_at=updated_at or datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(sim)
    db.flush()

    return sim


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
            case_hash="nested-hash-1",
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
            case_hash="nested-hash-2",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-02-01T00:00:00Z",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim1)
        db.flush()
        db.add(sim2)
        db.commit()

        res = client.get(f"{API_BASE}/cases")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1

        case_data = data[0]
        assert case_data["name"] == "test_case_nested"
        assert case_data["machineNames"] == [machine.name]
        assert case_data["hpcUsernames"] == []

        # Verify nested simulations are SimulationSummaryOut (lightweight)
        sims = case_data["simulations"]
        assert len(sims) == 2

        # Each summary should have only lightweight fields
        for s in sims:
            assert "id" in s
            assert "executionId" in s
            assert "caseHash" in s
            assert "status" in s
            assert "simulationStartDate" in s
            # Must NOT include heavy fields
            assert "machine" not in s
            assert "artifacts" not in s
            assert "links" not in s
            assert "groupedArtifacts" not in s
            assert "groupedLinks" not in s
            assert "runConfigDeltas" not in s
            assert "createdByUser" not in s

        # Verify case hash and summary payload shape
        exec_ids = {s["executionId"]: s for s in sims}
        assert exec_ids["case-nested-exec-1"]["caseHash"] == "nested-hash-1"
        assert exec_ids["case-nested-exec-2"]["caseHash"] == "nested-hash-2"


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

    def test_endpoint_returns_distinct_case_names_when_name_repeats(
        self, client, db: Session
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        _create_case(db, "dup_case")
        second_machine = Machine(
            name="dup-case-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(second_machine)
        db.flush()
        db.add(
            Case(
                name="dup_case",
                machine_id=second_machine.id,
                hpc_username="other-user",
            )
        )
        db.commit()

        res = client.get(f"{API_BASE}/cases/names")
        assert res.status_code == 200
        assert res.json() == ["dup_case"]


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
            case_hash="detail-hash-1",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            hpc_username="case-user",
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.flush()
        db.commit()

        res = client.get(f"{API_BASE}/cases/{case.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "test_case_detail"
        assert len(data["simulations"]) == 1
        assert data["machineNames"] == [machine.name]
        assert data["hpcUsernames"] == ["case-user"]
        assert data["simulations"][0]["executionId"] == "case-detail-exec-1"
        assert data["simulations"][0]["caseHash"] == "detail-hash-1"

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

    def test_validate_case_identity_accepts_trimmed_hpc_username(
        self, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_trimmed_hpc_username")

        assert (
            _validate_simulation_case_identity(
                case=case,
                machine_id=machine.id,
                hpc_username="  test-user  ",
            )
            == "test-user"
        )

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

    def test_manual_create_returns_generic_simulation_payload(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_first_manual_reference")
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

        db.refresh(case)
        assert data["caseId"] == str(case.id)
        assert data["caseName"] == case.name
        assert "isReference" not in data
        assert "changeCount" not in data
        assert "runConfigDeltas" not in data

    def test_endpoint_rejects_case_machine_mismatch(self, client, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_machine_mismatch")

        second_machine = Machine(
            name="test-case-machine-mismatch",
            site="Test Site",
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(second_machine)
        db.commit()

        payload = {
            "caseId": str(case.id),
            "executionId": "1081156.251218-200924",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "experimental",
            "status": "created",
            "machineId": str(second_machine.id),
            "simulationStartDate": "2023-01-01T00:00:00Z",
        }

        res = client.post(f"{API_BASE}/simulations", json=payload)

        assert res.status_code == 400
        assert "machine_id must match selected case identity" in res.json()["detail"]

    def test_endpoint_rejects_case_hpc_username_mismatch(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"
        case = _create_case(db, "test_case_hpc_mismatch")
        db.commit()

        payload = {
            "caseId": str(case.id),
            "executionId": "1081156.251218-200925",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "experimental",
            "status": "created",
            "machineId": str(machine.id),
            "simulationStartDate": "2023-01-01T00:00:00Z",
            "hpcUsername": "other-user",
        }

        res = client.post(f"{API_BASE}/simulations", json=payload)

        assert res.status_code == 400
        assert "hpc_username must match selected case identity" in res.json()["detail"]

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

        case = Case(
            id=case_id,
            name="reload_fail_case",
            machine_id=machine_id,
            hpc_username="test-user",
        )

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
        self, client, db: Session, normal_user_sync, admin_user_sync, monkeypatch
    ):
        monkeypatch.setattr(settings, "assistant_llm_enabled", False)
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
        assert data[0]["summaryCapabilities"] == {
            "llmAvailable": False,
            "autoGenerateDeterministicOnLoad": True,
        }

    def test_endpoint_reports_deterministic_only_capabilities_when_llm_misconfigured(
        self, client, db: Session, normal_user_sync, admin_user_sync, monkeypatch
    ):
        monkeypatch.setattr(settings, "assistant_llm_enabled", True)
        monkeypatch.setattr(settings, "assistant_llm_provider", "ollama")
        monkeypatch.setattr(settings, "assistant_ollama_model", None)
        monkeypatch.setattr(
            settings, "assistant_ollama_base_url", "http://localhost:11434"
        )
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        case = _create_case(db, "test_case_list_misconfigured")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_simulation_list_misconfigured",
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
            execution_id="list-test-exec-misconfigured",
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
        assert data[0]["summaryCapabilities"] == {
            "llmAvailable": False,
            "autoGenerateDeterministicOnLoad": True,
        }

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

        case_g1 = _create_case(db, "case_group1")
        case_g1.case_group = "ensemble_A"
        case_g2 = _create_case(db, "case_group2")
        case_g2.case_group = "ensemble_B"
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

    def test_filter_by_case_name_returns_simulations_across_normalized_cases(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        second_machine = Machine(
            name="normalized-case-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(second_machine)
        db.flush()

        first_case = _create_case(db, "normalized_case")
        second_case = Case(
            name="normalized_case",
            machine_id=second_machine.id,
            hpc_username="other-user",
        )
        db.add(second_case)
        db.flush()

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_filter_normalized_case_name",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=2,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        db.add_all(
            [
                Simulation(
                    case_id=first_case.id,
                    execution_id="normalized-exec-1",
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
                ),
                Simulation(
                    case_id=second_case.id,
                    execution_id="normalized-exec-2",
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    initialization_type="startup",
                    simulation_type="experimental",
                    status="created",
                    machine_id=second_machine.id,
                    simulation_start_date="2023-01-02T00:00:00Z",
                    created_by=normal_user_sync["id"],
                    last_updated_by=admin_user_sync["id"],
                    ingestion_id=ingestion.id,
                ),
            ]
        )
        db.commit()

        res = client.get(
            f"{API_BASE}/simulations", params={"case_name": "normalized_case"}
        )
        assert res.status_code == 200
        assert {sim["executionId"] for sim in res.json()} == {
            "normalized-exec-1",
            "normalized-exec-2",
        }

    def test_filter_by_case_name_and_case_group(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "combo_case")
        case.case_group = "combo_group"
        case_other = _create_case(db, "other_case")
        case_other.case_group = "combo_group"
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
        self, client, db: Session, normal_user_sync, admin_user_sync, monkeypatch
    ):
        monkeypatch.setattr(settings, "assistant_llm_enabled", True)
        monkeypatch.setattr(settings, "assistant_llm_provider", "ollama")
        monkeypatch.setattr(settings, "assistant_ollama_model", "gemma4:26b")
        monkeypatch.setattr(
            settings, "assistant_ollama_base_url", "http://localhost:11434"
        )
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
            case_hash="abc123casehash",
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
        assert data["summaryCapabilities"] == {
            "llmAvailable": True,
            "autoGenerateDeterministicOnLoad": False,
        }
        assert data["caseHash"] == "abc123casehash"

    def test_endpoint_reports_deterministic_only_capabilities_when_llm_misconfigured(
        self, client, db: Session, normal_user_sync, admin_user_sync, monkeypatch
    ):
        monkeypatch.setattr(settings, "assistant_llm_enabled", True)
        monkeypatch.setattr(settings, "assistant_llm_provider", "ollama")
        monkeypatch.setattr(settings, "assistant_ollama_model", None)
        monkeypatch.setattr(
            settings, "assistant_ollama_base_url", "http://localhost:11434"
        )
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        case = _create_case(db, "test_case_get_misconfigured")

        ingestion = Ingestion(
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="test_simulation_get_misconfigured",
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
            execution_id="get-test-exec-misconfigured",
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
        db.refresh(sim)

        res = client.get(f"{API_BASE}/simulations/{sim.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["summaryCapabilities"] == {
            "llmAvailable": False,
            "autoGenerateDeterministicOnLoad": True,
        }

    def test_endpoint_raises_404_if_simulation_not_found(self, client):
        res = client.get(f"{API_BASE}/simulations/{uuid4()}")
        assert res.status_code == 404
        assert res.json() == {"detail": "Simulation not found"}


class TestUpdateSimulation:
    def test_endpoint_updates_sparse_metadata_and_audit_fields(
        self, client, db: Session, normal_user_sync, admin_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch",
        )
        original_updated_at = datetime.now(timezone.utc) - timedelta(days=2)
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=admin_user_sync["id"],
            updated_at=original_updated_at,
        )
        db.commit()

        payload = {
            "simulationType": "production",
            "status": "completed",
            "description": "Updated description",
            "campaign": "campaign-updated",
            "notesMarkdown": "Updated notes",
        }

        res = client.patch(f"{API_BASE}/simulations/{sim.id}", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["simulationType"] == payload["simulationType"]
        assert data["status"] == payload["status"]
        assert data["description"] == payload["description"]
        assert data["campaign"] == payload["campaign"]
        assert data["notesMarkdown"] == payload["notesMarkdown"]
        assert data["compiler"] == "gcc"
        assert data["gitRepositoryUrl"] == "https://example.com/original"
        assert data["gitTag"] == "v1.0"
        assert data["hpcUsername"] == "old-user"
        assert data["lastUpdatedBy"] == str(normal_user_sync["id"])
        assert data["lastUpdatedByUser"]["email"] == normal_user_sync["email"]
        assert data["updatedAt"] != original_updated_at.isoformat()

        db.expire_all()
        updated_sim = db.query(Simulation).filter(Simulation.id == sim.id).one()
        assert updated_sim.simulation_type == payload["simulationType"]
        assert updated_sim.status == payload["status"]
        assert updated_sim.description == payload["description"]
        assert updated_sim.campaign == payload["campaign"]
        assert updated_sim.notes_markdown == payload["notesMarkdown"]
        assert updated_sim.compiler == "gcc"
        assert updated_sim.git_repository_url == "https://example.com/original"
        assert updated_sim.git_tag == "v1.0"
        assert updated_sim.last_updated_by == normal_user_sync["id"]
        assert updated_sim.updated_at > original_updated_at

    def test_endpoint_replaces_artifacts_and_links(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_resources")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_resources",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-resources",
        )
        sim.artifacts.extend(
            [
                Artifact(kind="output", uri="/tmp/output-old", label="Old output"),
                Artifact(kind="archive", uri="/tmp/archive-old", label="Old archive"),
            ]
        )
        sim.links.extend(
            [
                ExternalLink(
                    kind="diagnostic",
                    url="https://example.com/diagnostic-old",
                    label="Old diagnostic",
                ),
                ExternalLink(
                    kind="performance",
                    url="https://example.com/performance-old",
                    label="Old performance",
                ),
            ]
        )
        db.commit()

        payload = {
            "artifacts": [
                {
                    "kind": "output",
                    "uri": "  /tmp/output-new  ",
                    "label": "  New output  ",
                },
                {
                    "kind": "run_script",
                    "uri": "s3://bucket/run.sh",
                    "label": "Run script",
                },
            ],
            "links": [
                {
                    "kind": "diagnostic",
                    "url": "https://example.com/diagnostic-new",
                    "label": "Updated diagnostics",
                },
                {
                    "kind": "docs",
                    "url": "https://example.com/docs/new",
                    "label": "Docs",
                },
            ],
        }

        res = client.patch(f"{API_BASE}/simulations/{sim.id}", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert {artifact["uri"] for artifact in data["artifacts"]} == {
            "/tmp/output-new",
            "s3://bucket/run.sh",
        }
        assert {artifact["kind"] for artifact in data["artifacts"]} == {
            "output",
            "run_script",
        }
        assert data["groupedArtifacts"]["output"][0]["label"] == "New output"
        assert (
            data["groupedLinks"]["diagnostic"][0]["url"]
            == "https://example.com/diagnostic-new"
        )
        assert data["groupedLinks"]["docs"][0]["label"] == "Docs"

        db.expire_all()
        updated_sim = db.query(Simulation).filter(Simulation.id == sim.id).one()
        assert {
            (artifact.kind.value, artifact.uri) for artifact in updated_sim.artifacts
        } == {
            ("output", "/tmp/output-new"),
            ("run_script", "s3://bucket/run.sh"),
        }
        assert {(link.kind.value, link.url) for link in updated_sim.links} == {
            ("diagnostic", "https://example.com/diagnostic-new"),
            ("docs", "https://example.com/docs/new"),
        }
        assert db.query(Artifact).filter(Artifact.simulation_id == sim.id).count() == 2
        assert (
            db.query(ExternalLink).filter(ExternalLink.simulation_id == sim.id).count()
            == 2
        )

    def test_endpoint_can_clear_artifacts_and_links(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_clear_resources")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_clear_resources",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-clear-resources",
        )
        sim.artifacts.append(
            Artifact(kind="output", uri="/tmp/output-old", label="Old output")
        )
        sim.links.append(
            ExternalLink(
                kind="diagnostic",
                url="https://example.com/diagnostic-old",
                label="Old diagnostic",
            )
        )
        db.commit()

        res = client.patch(
            f"{API_BASE}/simulations/{sim.id}",
            json={"artifacts": [], "links": []},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["artifacts"] == []
        assert data["links"] == []
        assert data["groupedArtifacts"] == {}
        assert data["groupedLinks"] == {}

        db.expire_all()
        assert db.query(Artifact).filter(Artifact.simulation_id == sim.id).count() == 0
        assert (
            db.query(ExternalLink).filter(ExternalLink.simulation_id == sim.id).count()
            == 0
        )

    def test_endpoint_returns_401_without_authentication(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_unauth")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_unauth",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-unauth",
        )
        db.commit()

        app.dependency_overrides.pop(current_active_user, None)

        res = client.patch(
            f"{API_BASE}/simulations/{sim.id}",
            json={"description": "Should fail"},
        )

        assert res.status_code == 401

    def test_plain_user_gets_403_for_patch(self, client, db: Session, normal_user_sync):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_forbidden_user")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_forbidden_user",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-forbidden-user",
        )
        db.commit()

        _override_current_user(
            user_id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            role=UserRole.USER,
            has_membership=False,
        )

        res = client.patch(
            f"{API_BASE}/simulations/{sim.id}",
            json={"description": "Should fail"},
        )

        assert res.status_code == 403
        assert "verified E3SM GitHub organization membership" in res.json()["detail"]

    def test_admin_can_patch_without_org_membership(
        self, client, db: Session, admin_user_sync, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_admin")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_admin",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-admin",
        )
        db.commit()

        _override_current_user(
            user_id=admin_user_sync["id"],
            email=admin_user_sync["email"],
            role=UserRole.ADMIN,
            has_membership=False,
        )

        res = client.patch(
            f"{API_BASE}/simulations/{sim.id}",
            json={"description": "Admin update"},
        )

        assert res.status_code == 200
        assert res.json()["description"] == "Admin update"

    def test_endpoint_returns_404_when_simulation_not_found(self, client):
        res = client.patch(
            f"{API_BASE}/simulations/{uuid4()}",
            json={"description": "Missing simulation"},
        )

        assert res.status_code == 404
        assert res.json() == {"detail": "Simulation not found"}

    @pytest.mark.parametrize(
        "payload",
        [
            {"compiler": "intel"},
            {"gitRepositoryUrl": "https://example.com/updated"},
            {"gitBranch": "feature/test"},
            {"gitTag": "v2.0"},
            {"gitCommitHash": "deadbeef"},
        ],
    )
    def test_endpoint_rejects_out_of_scope_fields(
        self, client, db: Session, normal_user_sync, payload
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_scope")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_scope",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-scope",
        )
        db.commit()

        res = client.patch(f"{API_BASE}/simulations/{sim.id}", json=payload)

        assert res.status_code == 422

        db.expire_all()
        unchanged_sim = db.query(Simulation).filter(Simulation.id == sim.id).one()
        assert unchanged_sim.description == "Original description"
        assert unchanged_sim.compiler == "gcc"
        assert unchanged_sim.case_id == case.id

    @pytest.mark.parametrize("payload", [{"status": None}, {"simulationType": None}])
    def test_endpoint_rejects_explicit_null_for_enum_fields(
        self, client, db: Session, normal_user_sync, payload
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_null_enum")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_null_enum",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-null-enum",
        )
        db.commit()

        original_updated_at = sim.updated_at

        res = client.patch(f"{API_BASE}/simulations/{sim.id}", json=payload)

        assert res.status_code == 422

        db.expire_all()
        unchanged_sim = db.query(Simulation).filter(Simulation.id == sim.id).one()
        assert unchanged_sim.status == SimulationStatus.CREATED
        assert unchanged_sim.simulation_type == SimulationType.EXPERIMENTAL
        assert unchanged_sim.updated_at == original_updated_at

    @pytest.mark.parametrize(
        "payload",
        [
            {"links": [{"kind": "diagnostic", "url": "not-a-url", "label": "Bad"}]},
            {"artifacts": [{"kind": "output", "uri": "   ", "label": "Bad"}]},
            {"artifacts": [{"kind": "output", "uri": None, "label": "Bad"}]},
            {"artifacts": [{"kind": "output", "uri": 123, "label": "Bad"}]},
            {
                "links": [
                    {
                        "kind": "docs",
                        "url": "https://example.com/docs",
                        "label": "One",
                    },
                    {
                        "kind": "docs",
                        "url": "https://example.com/docs",
                        "label": "Two",
                    },
                ]
            },
        ],
    )
    def test_endpoint_rejects_invalid_resource_payloads(
        self, client, db: Session, normal_user_sync, payload
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_invalid_resources")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_invalid_resources",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-invalid-resources",
        )
        db.commit()

        res = client.patch(f"{API_BASE}/simulations/{sim.id}", json=payload)

        assert res.status_code == 422

    def test_endpoint_rejects_hpc_username_mismatch(
        self, client, db: Session, normal_user_sync
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_patch_hpc_identity")
        ingestion = _create_ingestion(
            db,
            machine.id,
            normal_user_sync["id"],
            source_reference="test_simulation_patch_hpc_identity",
        )
        sim = _create_simulation_record(
            db,
            case=case,
            machine_id=machine.id,
            ingestion_id=ingestion.id,
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            execution_id="patch-test-hpc-identity",
        )
        db.commit()

        res = client.patch(
            f"{API_BASE}/simulations/{sim.id}",
            json={"hpcUsername": "other-user"},
        )

        assert res.status_code == 400
        assert "hpc_username must match selected case identity" in res.json()["detail"]

        db.expire_all()
        unchanged_sim = db.query(Simulation).filter(Simulation.id == sim.id).one()
        assert unchanged_sim.hpc_username == "old-user"

    def test_update_simulation_raises_500_when_reload_fails(self) -> None:
        sim_id = uuid4()
        user_id = uuid4()

        payload = SimulationUpdate.model_validate({"description": "Updated"})

        user = User(
            id=user_id,
            email="reload-fail@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
            has_verified_e3sm_membership=True,
        )

        sim = MagicMock()
        sim_query = MagicMock()
        sim_query.filter.return_value.one_or_none.return_value = sim

        detail_query = MagicMock()
        detail_query.filter.return_value.one_or_none.return_value = None

        db = MagicMock(spec=Session)
        db.query.return_value = sim_query

        with patch(
            "app.features.simulation.api._simulation_detail_query",
            return_value=detail_query,
        ):
            with patch(
                "app.features.simulation.api.transaction",
                return_value=nullcontext(),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    update_simulation(
                        sim_id=sim_id,
                        payload=payload,
                        db=db,
                        user=user,
                    )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to load updated simulation."


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
