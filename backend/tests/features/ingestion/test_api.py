"""Tests for the ingestion API endpoints.

This test module provides comprehensive coverage for the ingestion API,
including path-based and upload-based ingestion endpoints.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.ingestion.api import (
    _build_hpc_upload_payload,
    _build_ingestion_state_response,
    _normalize_processed_execution_ids,
    _run_ingest_archive,
    _save_uploaded_file_and_hash,
    _validate_archive_path,
    _validate_upload_file,
    ingest_from_hpc_upload,
    ingest_from_upload,
    persist_execution_discovery_results,
)
from app.features.ingestion.enums import (
    ExecutionDiscoveryOutcome,
    IngestionSourceType,
    IngestionStatus,
)
from app.features.ingestion.ingest import IngestArchiveResult
from app.features.ingestion.models import ExecutionDiscoveryResult, Ingestion
from app.features.ingestion.parsers.parser import ArchiveValidationError
from app.features.ingestion.parsers.types import ParsedSimulation
from app.features.ingestion.schemas import (
    ExecutionDiscoveryResultsRequest,
    IngestionStateResponse,
)
from app.features.machine.models import Machine
from app.features.simulation.enums import ArtifactKind
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
            role=UserRole.ADMIN,
        )

    app.dependency_overrides[current_active_user] = fake_current_user

    yield
    app.dependency_overrides.clear()


# Override dependency to simulate a non-admin user
def fake_non_admin_user():
    return User(
        id=1,
        email="user@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.USER,
    )


def _create_case(
    db: Session,
    name: str,
    *,
    machine: Machine | None = None,
    hpc_username: str = "test-user",
    case_group: str | None = None,
) -> Case:
    if machine is None:
        machine = db.query(Machine).first()
        assert machine is not None

    case = Case(
        name=name,
        machine_id=machine.id,
        hpc_username=hpc_username,
        case_group=case_group,
    )
    db.add(case)
    db.flush()
    return case


class TestExecutionDiscoveryResultsEndpoint:
    @staticmethod
    def _persist_concurrently(
        bind, payloads: list[ExecutionDiscoveryResultsRequest]
    ) -> list[str]:
        user = User(
            id=uuid.uuid4(),
            email="concurrency@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.ADMIN,
        )

        def persist(payload: ExecutionDiscoveryResultsRequest) -> str:
            session = Session(bind=bind)
            try:
                persist_execution_discovery_results(
                    payload,
                    db=session,
                    user=user,
                )
                return "success"
            except HTTPException as exc:
                return f"http_{exc.status_code}"
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(persist, payloads))

    def test_batch_insert_is_idempotent_and_visible_in_state(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        payload = {
            "machine_name": machine.name,
            "results": [
                {
                    "case_identity": "campaign/case-a",
                    "execution_id": "100.1-1",
                    "outcome": "accepted",
                },
                {
                    "case_identity": "campaign/case-a",
                    "execution_id": "101.1-1",
                    "outcome": "rejected_incomplete",
                },
            ],
        }

        first = client.post(f"{API_BASE}/ingestions/discovery-results", json=payload)
        second = client.post(f"{API_BASE}/ingestions/discovery-results", json=payload)

        assert first.status_code == 201
        assert first.json() == {"inserted_count": 2, "existing_count": 0}
        assert second.status_code == 201
        assert second.json() == {"inserted_count": 0, "existing_count": 2}
        state = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": machine.name}
        )
        assert state.status_code == 200
        assert (
            state.json()["discovery_results"]["campaign/case-a"] == payload["results"]
        )

    def test_idempotency_reread_loads_only_requested_composite_identity(
        self, client, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        machine_name = machine.name
        case_identity = f"bounded-reread-{uuid.uuid4()}"
        db.add_all(
            [
                ExecutionDiscoveryResult(
                    machine_id=machine.id,
                    case_identity=case_identity,
                    execution_id=execution_id,
                    outcome=ExecutionDiscoveryOutcome.ACCEPTED,
                )
                for execution_id in ("100.1-1", "unrelated.1-1")
            ]
        )
        db.commit()
        db.expunge_all()
        loaded_execution_ids: list[str] = []

        def record_load(result: ExecutionDiscoveryResult, _: Any) -> None:
            loaded_execution_ids.append(result.execution_id)

        event.listen(ExecutionDiscoveryResult, "load", record_load)
        try:
            response = client.post(
                f"{API_BASE}/ingestions/discovery-results",
                json={
                    "machine_name": machine_name,
                    "results": [
                        {
                            "case_identity": case_identity,
                            "execution_id": "100.1-1",
                            "outcome": "accepted",
                        }
                    ],
                },
            )
        finally:
            event.remove(ExecutionDiscoveryResult, "load", record_load)

        assert response.status_code == 201
        assert loaded_execution_ids == ["100.1-1"]

    def test_conflicting_stored_outcome_returns_409(self, client, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        base: dict[str, Any] = {
            "machine_name": machine.name,
            "results": [
                {
                    "case_identity": "case-a",
                    "execution_id": "100.1-1",
                    "outcome": "accepted",
                }
            ],
        }
        assert (
            client.post(
                f"{API_BASE}/ingestions/discovery-results", json=base
            ).status_code
            == 201
        )
        base["results"][0]["outcome"] = "rejected_invalid"

        response = client.post(f"{API_BASE}/ingestions/discovery-results", json=base)

        assert response.status_code == 409
        stored = db.query(ExecutionDiscoveryResult).one()
        assert stored.outcome == ExecutionDiscoveryOutcome.ACCEPTED

    def test_conflicting_batch_rolls_back_new_rows(self, client, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        endpoint = f"{API_BASE}/ingestions/discovery-results"
        existing = {
            "case_identity": "case-a",
            "execution_id": "100.1-1",
            "outcome": "accepted",
        }
        assert (
            client.post(
                endpoint,
                json={"machine_name": machine.name, "results": [existing]},
            ).status_code
            == 201
        )

        response = client.post(
            endpoint,
            json={
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": "case-a",
                        "execution_id": "101.1-1",
                        "outcome": "accepted",
                    },
                    {**existing, "outcome": "rejected_invalid"},
                ],
            },
        )

        assert response.status_code == 409
        assert (
            db.query(ExecutionDiscoveryResult)
            .filter(ExecutionDiscoveryResult.execution_id == "101.1-1")
            .one_or_none()
            is None
        )

    def test_concurrent_identical_inserts_both_succeed(self, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        identity = f"concurrent-identical-{uuid.uuid4()}"
        payload = ExecutionDiscoveryResultsRequest.model_validate(
            {
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": identity,
                        "execution_id": "100.1-1",
                        "outcome": "accepted",
                    }
                ],
            }
        )

        results = self._persist_concurrently(db.get_bind().engine, [payload, payload])

        assert results == ["success", "success"]
        assert (
            db.query(ExecutionDiscoveryResult)
            .filter(ExecutionDiscoveryResult.case_identity == identity)
            .count()
            == 1
        )

    def test_concurrent_differing_inserts_store_one_and_conflict_one(
        self, db: Session
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        identity = f"concurrent-conflict-{uuid.uuid4()}"
        base = ExecutionDiscoveryResultsRequest.model_validate(
            {
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": identity,
                        "execution_id": "100.1-1",
                        "outcome": "accepted",
                    }
                ],
            }
        )
        conflicting = ExecutionDiscoveryResultsRequest.model_validate(
            {
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": identity,
                        "execution_id": "100.1-1",
                        "outcome": "rejected_invalid",
                    }
                ],
            }
        )

        results = self._persist_concurrently(db.get_bind().engine, [base, conflicting])

        assert sorted(results) == ["http_409", "success"]
        assert (
            db.query(ExecutionDiscoveryResult)
            .filter(ExecutionDiscoveryResult.case_identity == identity)
            .count()
            == 1
        )

    def test_conflicting_batch_input_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionDiscoveryResultsRequest.model_validate(
                {
                    "machine_name": "perlmutter",
                    "results": [
                        {
                            "case_identity": "case-a",
                            "execution_id": "100.1-1",
                            "outcome": "accepted",
                        },
                        {
                            "case_identity": "case-a",
                            "execution_id": "100.1-1",
                            "outcome": "rejected_invalid",
                        },
                    ],
                }
            )

    def test_non_admin_is_forbidden(self, client, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        app.dependency_overrides[current_active_user] = fake_non_admin_user

        response = client.post(
            f"{API_BASE}/ingestions/discovery-results",
            json={
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": "case-a",
                        "execution_id": "100.1-1",
                        "outcome": "accepted",
                    }
                ],
            },
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("field", ["case_identity", "execution_id"])
    def test_blank_identifiers_are_rejected(
        self, client, db: Session, field: str
    ) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        result = {
            "case_identity": "case-a",
            "execution_id": "100.1-1",
            "outcome": "accepted",
        }
        result[field] = "   "

        response = client.post(
            f"{API_BASE}/ingestions/discovery-results",
            json={"machine_name": machine.name, "results": [result]},
        )

        assert response.status_code == 422

    def test_machine_and_case_identity_are_isolated(self, client, db: Session) -> None:
        first_machine = TestGetIngestionStateEndpoint._create_machine(
            db, f"machine-a-{uuid.uuid4()}"
        )
        second_machine = TestGetIngestionStateEndpoint._create_machine(
            db, f"machine-b-{uuid.uuid4()}"
        )
        endpoint = f"{API_BASE}/ingestions/discovery-results"

        for machine, case_identity, outcome in (
            (first_machine, "case-a", "accepted"),
            (first_machine, "case-b", "rejected_invalid"),
            (second_machine, "case-a", "rejected_incomplete"),
        ):
            response = client.post(
                endpoint,
                json={
                    "machine_name": machine.name,
                    "results": [
                        {
                            "case_identity": case_identity,
                            "execution_id": "100.1-1",
                            "outcome": outcome,
                        }
                    ],
                },
            )
            assert response.status_code == 201

        first_state = client.get(
            f"{API_BASE}/ingestions/state",
            params={"machine_name": first_machine.name},
        ).json()["discovery_results"]
        second_state = client.get(
            f"{API_BASE}/ingestions/state",
            params={"machine_name": second_machine.name},
        ).json()["discovery_results"]

        assert set(first_state) == {"case-a", "case-b"}
        assert first_state["case-a"][0]["outcome"] == "accepted"
        assert second_state["case-a"][0]["outcome"] == "rejected_incomplete"

    def test_service_account_is_authorized(self, client, db: Session) -> None:
        machine = db.query(Machine).first()
        assert machine is not None
        app.dependency_overrides[current_active_user] = lambda: User(
            id=uuid.uuid4(),
            email="service@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.SERVICE_ACCOUNT,
        )

        response = client.post(
            f"{API_BASE}/ingestions/discovery-results",
            json={
                "machine_name": machine.name,
                "results": [
                    {
                        "case_identity": "case-a",
                        "execution_id": "100.1-1",
                        "outcome": "accepted",
                    }
                ],
            },
        )

        assert response.status_code == 201

    def test_state_response_defaults_missing_discovery_results(self) -> None:
        state = IngestionStateResponse.model_validate(
            {"machine_name": "perlmutter", "cases": {}}
        )

        assert state.discovery_results == {}


class TestGetIngestionStateEndpoint:
    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        machine = db.query(Machine).filter(Machine.name == name).one_or_none()
        if machine is not None:
            return machine

        machine = Machine(
            name=name,
            site="Test Site",
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(machine)
        db.flush()
        return machine

    @staticmethod
    def _create_ingestion_with_simulation(
        db: Session,
        *,
        user_id,
        machine: Machine,
        source_type: IngestionSourceType,
        source_reference: str,
        execution_id: str,
        case_name: str,
    ) -> None:
        case = _create_case(db, case_name, machine=machine)

        ingestion = Ingestion(
            source_type=source_type,
            source_reference=source_reference,
            machine_id=machine.id,
            triggered_by=user_id,
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
            processed_execution_ids=[execution_id],
        )
        db.add(ingestion)
        db.flush()

        db.add(
            Simulation(
                case_id=case.id,
                execution_id=execution_id,
                compset="FHIST",
                compset_alias="fhist",
                grid_name="ne30pg2_r05_IcoswISC30E3r5",
                grid_resolution="1x1",
                simulation_type="production",
                status="completed",
                initialization_type="branch",
                simulation_start_date=datetime.now(timezone.utc),
                created_by=user_id,
                last_updated_by=user_id,
                ingestion_id=ingestion.id,
            )
        )

    def test_endpoint_aggregates_hpc_path_and_hpc_upload_state_and_excludes_browser_uploads(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        user_id = normal_user_sync["id"]

        self._create_ingestion_with_simulation(
            db,
            user_id=user_id,
            machine=machine,
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/case_a",
            execution_id="101.1-1",
            case_name="state_case_a_1",
        )
        self._create_ingestion_with_simulation(
            db,
            user_id=user_id,
            machine=machine,
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/case_a",
            execution_id="100.1-1",
            case_name="state_case_a_2",
        )
        self._create_ingestion_with_simulation(
            db,
            user_id=user_id,
            machine=machine,
            source_type=IngestionSourceType.HPC_UPLOAD,
            source_reference="/archive/case_upload",
            execution_id="102.1-1",
            case_name="state_case_upload_hpc",
        )
        self._create_ingestion_with_simulation(
            db,
            user_id=user_id,
            machine=machine,
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference="upload.zip",
            execution_id="999.1-1",
            case_name="state_case_upload",
        )
        db.commit()

        res = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": "perlmutter"}
        )

        assert res.status_code == 200
        data = res.json()
        assert data["machine_name"] == "perlmutter"
        assert list(data["cases"]) == ["/archive/case_a", "/archive/case_upload"]
        assert data["cases"]["/archive/case_a"]["processed_execution_ids"] == [
            "100.1-1",
            "101.1-1",
        ]
        assert data["cases"]["/archive/case_upload"]["processed_execution_ids"] == [
            "102.1-1"
        ]
        assert isinstance(data["cases"]["/archive/case_a"]["fingerprint"], str)

    def test_endpoint_accepts_machine_alias(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        self._create_ingestion_with_simulation(
            db,
            user_id=normal_user_sync["id"],
            machine=machine,
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/case_alias",
            execution_id="200.1-1",
            case_name="state_case_alias",
        )
        db.commit()

        res = client.get(f"{API_BASE}/ingestions/state", params={"machine_name": "pm"})

        assert res.status_code == 200
        assert res.json()["machine_name"] == "perlmutter"

    def test_endpoint_uses_persisted_processed_execution_ids_for_partial_and_duplicate_only_cases(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        user_id = normal_user_sync["id"]

        partial_case = _create_case(db, "state_case_partial", machine=machine)

        partial_ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/case_partial",
            machine_id=machine.id,
            triggered_by=user_id,
            status=IngestionStatus.PARTIAL,
            created_count=1,
            duplicate_count=0,
            error_count=1,
            processed_execution_ids=["100.1-1", "101.1-1"],
        )
        db.add(partial_ingestion)
        db.flush()
        db.add(
            Simulation(
                case_id=partial_case.id,
                execution_id="100.1-1",
                compset="FHIST",
                compset_alias="fhist",
                grid_name="grid",
                grid_resolution="1x1",
                simulation_type="production",
                status="completed",
                initialization_type="branch",
                simulation_start_date=datetime.now(timezone.utc),
                created_by=user_id,
                last_updated_by=user_id,
                ingestion_id=partial_ingestion.id,
            )
        )

        duplicate_only_ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/case_duplicate_only",
            machine_id=machine.id,
            triggered_by=user_id,
            status=IngestionStatus.FAILED,
            created_count=0,
            duplicate_count=1,
            error_count=0,
            processed_execution_ids=["200.1-1"],
        )
        db.add(duplicate_only_ingestion)
        db.commit()

        res = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": "perlmutter"}
        )

        assert res.status_code == 200
        data = res.json()["cases"]
        assert data["/archive/case_partial"]["processed_execution_ids"] == [
            "100.1-1",
            "101.1-1",
        ]
        assert data["/archive/case_duplicate_only"]["processed_execution_ids"] == [
            "200.1-1"
        ]

    def test_endpoint_falls_back_to_simulation_ids_for_legacy_ingestions_without_persisted_state(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        case = _create_case(db, "legacy_state_case", machine=machine)

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/legacy_case",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
            processed_execution_ids=None,
        )
        db.add(ingestion)
        db.flush()
        db.add(
            Simulation(
                case_id=case.id,
                execution_id="legacy-100.1-1",
                compset="FHIST",
                compset_alias="fhist",
                grid_name="grid",
                grid_resolution="1x1",
                simulation_type="production",
                status="completed",
                initialization_type="branch",
                simulation_start_date=datetime.now(timezone.utc),
                created_by=normal_user_sync["id"],
                last_updated_by=normal_user_sync["id"],
                ingestion_id=ingestion.id,
            )
        )
        db.commit()

        res = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": "perlmutter"}
        )

        assert res.status_code == 200
        assert res.json()["cases"]["/archive/legacy_case"][
            "processed_execution_ids"
        ] == ["legacy-100.1-1"]

    def test_endpoint_falls_back_to_simulation_ids_for_legacy_hpc_upload_ingestions_without_persisted_state(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        case = _create_case(db, "legacy_hpc_upload_case", machine=machine)

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_UPLOAD,
            source_reference="/archive/legacy_upload_case",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
            processed_execution_ids=None,
        )
        db.add(ingestion)
        db.flush()
        db.add(
            Simulation(
                case_id=case.id,
                execution_id="legacy-upload-100.1-1",
                compset="FHIST",
                compset_alias="fhist",
                grid_name="grid",
                grid_resolution="1x1",
                simulation_type="production",
                status="completed",
                initialization_type="branch",
                simulation_start_date=datetime.now(timezone.utc),
                created_by=normal_user_sync["id"],
                last_updated_by=normal_user_sync["id"],
                ingestion_id=ingestion.id,
            )
        )
        db.commit()

        res = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": "perlmutter"}
        )

        assert res.status_code == 200
        assert res.json()["cases"]["/archive/legacy_upload_case"][
            "processed_execution_ids"
        ] == ["legacy-upload-100.1-1"]

    def test_endpoint_handles_many_legacy_ingestions_without_persisted_state(
        self, client, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        user_id = normal_user_sync["id"]

        legacy_case_count = 200

        for index in range(legacy_case_count):
            case = _create_case(db, f"legacy_state_case_{index}", machine=machine)

            ingestion = Ingestion(
                source_type=IngestionSourceType.HPC_PATH,
                source_reference=f"/archive/legacy_case_{index}",
                machine_id=machine.id,
                triggered_by=user_id,
                status=IngestionStatus.SUCCESS,
                created_count=1,
                duplicate_count=0,
                error_count=0,
                processed_execution_ids=None,
            )
            db.add(ingestion)
            db.flush()

            db.add(
                Simulation(
                    case_id=case.id,
                    execution_id=f"legacy-{index}.1-1",
                    compset="FHIST",
                    compset_alias="fhist",
                    grid_name="grid",
                    grid_resolution="1x1",
                    simulation_type="production",
                    status="completed",
                    initialization_type="branch",
                    simulation_start_date=datetime.now(timezone.utc),
                    created_by=user_id,
                    last_updated_by=user_id,
                    ingestion_id=ingestion.id,
                )
            )

        db.commit()

        res = client.get(
            f"{API_BASE}/ingestions/state", params={"machine_name": "perlmutter"}
        )

        assert res.status_code == 200
        data = res.json()["cases"]
        assert len(data) == legacy_case_count
        assert data["/archive/legacy_case_0"]["processed_execution_ids"] == [
            "legacy-0.1-1"
        ]
        assert data["/archive/legacy_case_199"]["processed_execution_ids"] == [
            "legacy-199.1-1"
        ]

    def test_endpoint_returns_404_when_machine_missing(self, client) -> None:
        res = client.get(
            f"{API_BASE}/ingestions/state",
            params={"machine_name": "does-not-exist-machine"},
        )

        assert res.status_code == 404

    def test_endpoint_returns_403_for_non_admin_user(self, client) -> None:
        app.dependency_overrides[current_active_user] = fake_non_admin_user

        res = client.get(
            f"{API_BASE}/ingestions/state",
            params={"machine_name": "perlmutter"},
        )

        app.dependency_overrides.clear()

        assert res.status_code == 403
        assert (
            res.json()["detail"]
            == "Only administrators and service accounts may read ingestion state."
        )

    def test_endpoint_returns_401_without_authentication(self, client) -> None:
        app.dependency_overrides.clear()

        res = client.get(
            f"{API_BASE}/ingestions/state",
            params={"machine_name": "perlmutter"},
        )

        assert res.status_code == 401

    def test_build_ingestion_state_response_skips_blank_case_paths_and_blank_fallback_execution_ids(
        self, db: Session, normal_user_sync
    ) -> None:
        machine = self._create_machine(db, "perlmutter")
        user_id = normal_user_sync["id"]

        db.add(
            Ingestion(
                source_type=IngestionSourceType.HPC_PATH,
                source_reference="",
                machine_id=machine.id,
                triggered_by=user_id,
                status=IngestionStatus.SUCCESS,
                created_count=0,
                duplicate_count=1,
                error_count=0,
                processed_execution_ids=["100.1-1"],
            )
        )

        blank_execution_case = _create_case(db, "blank_execution_case", machine=machine)

        blank_execution_ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/blank_execution",
            machine_id=machine.id,
            triggered_by=user_id,
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
            processed_execution_ids=None,
        )
        db.add(blank_execution_ingestion)
        db.flush()
        db.add(
            Simulation(
                case_id=blank_execution_case.id,
                execution_id="",
                compset="FHIST",
                compset_alias="fhist",
                grid_name="grid",
                grid_resolution="1x1",
                simulation_type="production",
                status="completed",
                initialization_type="branch",
                simulation_start_date=datetime.now(timezone.utc),
                created_by=user_id,
                last_updated_by=user_id,
                ingestion_id=blank_execution_ingestion.id,
            )
        )

        self._create_ingestion_with_simulation(
            db,
            user_id=user_id,
            machine=machine,
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive/valid_case",
            execution_id="200.1-1",
            case_name="state_case_valid",
        )
        db.commit()

        response = _build_ingestion_state_response(db, machine.id, machine.name)

        assert response.cases.keys() == {"/archive/valid_case"}
        assert response.cases["/archive/valid_case"].processed_execution_ids == [
            "200.1-1"
        ]

    def test_normalize_processed_execution_ids_returns_none_for_non_list(self) -> None:
        assert _normalize_processed_execution_ids("not-a-list") is None


class TestIngestFromPathEndpoint:
    @staticmethod
    def _create_archive_file(
        tmp_path, name: str = "archive.tar.gz", content: bytes = b"x"
    ):
        archive_path = tmp_path / name
        archive_path.write_bytes(content)

        return archive_path

    def test_endpoint_returns_403_for_non_admin_user(
        self, client, db: Session, tmp_path
    ):
        """Test that non-admin users receive a 403 Forbidden response."""
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        app.dependency_overrides[current_active_user] = fake_non_admin_user

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        # Restore dependency overrides
        app.dependency_overrides.clear()

        assert res.status_code == 403
        assert (
            res.json()["detail"]
            == "Only administrators and service accounts may ingest from filesystem paths."
        )

    def test_endpoint_returns_summary(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = _create_case(db, "test_case", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-summary-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0

    def test_endpoint_returns_409_on_conflict(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ValueError("Duplicate simulation"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 409
        assert res.json()["detail"] == "Duplicate simulation"

    def test_endpoint_includes_errors_in_response(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case1 = _create_case(db, "test_case_errors", machine=machine)
        case2 = _create_case(db, "case2_errors", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case1.id),
                    "executionId": "exec-errors-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            ),
            SimulationCreate.model_validate(
                {
                    "caseId": str(case2.id),
                    "executionId": "exec-errors-2",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "def456",
                }
            ),
        ]
        mock_errors = [{"file": "sim2.json", "error": "Invalid format"}]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=2,
                duplicate_count=0,
                errors=mock_errors,
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        data = res.json()

        assert data["created_count"] == 2
        assert data["duplicate_count"] == 0
        assert data["errors"] == mock_errors

        assert len(data["simulations"]) == 2
        assert {simulation["execution_id"] for simulation in data["simulations"]} == {
            "exec-errors-1",
            "exec-errors-2",
        }
        assert {simulation["case_name"] for simulation in data["simulations"]} == {
            "test_case_errors",
            "case2_errors",
        }

    def test_endpoint_creates_audit_record(self, client, db: Session, tmp_path):
        """Test that ingestion creates an audit record in the database."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_content = b"audit-archive-content"
        archive_path = self._create_archive_file(
            tmp_path, "test.tar.gz", archive_content
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = _create_case(db, "test_case_audit", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-audit-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            client.post(f"{API_BASE}/ingestions/from-path", json=payload)
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert str(ingestion.source_type) == "hpc_path"
        assert ingestion.status == "success"
        assert ingestion.created_count == 1
        assert ingestion.duplicate_count == 0
        assert ingestion.error_count == 0
        assert ingestion.archive_sha256 is None

    def test_endpoint_persists_processed_execution_ids_when_provided(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {
            "archive_path": str(archive_path),
            "machine_name": machine.name,
            "processed_execution_ids": ["100.1-1", "101.1-1"],
        }

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[],
                created_count=0,
                duplicate_count=2,
                errors=[{"execution_dir": "x", "error": "duplicate"}],
            ),
        ):
            client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert ingestion.processed_execution_ids == ["100.1-1", "101.1-1"]

    def test_endpoint_returns_400_when_archive_path_missing(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        missing_path = tmp_path / "missing.tar.gz"
        payload = {"archive_path": str(missing_path), "machine_name": machine.name}

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert res.json()["detail"] == f"Archive path '{missing_path}' does not exist."

    def test_endpoint_returns_500_when_ingest_fails(
        self, client, db: Session, tmp_path
    ):
        """Test that a 500 is returned when archive processing fails."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "bad.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("processing failed"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 500
        assert "processing failed" in res.json()["detail"]

    def test_endpoint_returns_404_when_machine_not_found(self, client, tmp_path):
        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {
            "archive_path": str(archive_path),
            "machine_name": "does-not-exist-machine",
        }

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 404
        assert res.json()["detail"] == "Machine 'does-not-exist-machine' not found."

    @pytest.mark.parametrize("machine_alias", ["pm", "pm-cpu", "pm-gpu"])
    def test_endpoint_accepts_perlmutter_aliases(
        self, client, db: Session, tmp_path, machine_alias: str
    ):
        machine = db.query(Machine).filter(Machine.name == "perlmutter").first()
        if machine is None:
            machine = Machine(
                name="perlmutter",
                site="NERSC",
                architecture="AMD EPYC + NVIDIA A100",
                scheduler="slurm",
                gpu=True,
            )
            db.add(machine)
            db.commit()
            db.refresh(machine)

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine_alias}

        case = _create_case(db, f"test_case_alias_{machine_alias}", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": f"exec-{machine_alias}",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201


class TestIngestFromUploadEndpoint:
    @staticmethod
    def _create_archive_file(
        tmp_path, name: str = "archive.tar.gz", content: bytes = b"x"
    ):
        archive_path = tmp_path / name
        archive_path.write_bytes(content)

        return archive_path

    def test_upload_valid_zip_file(self, client, db: Session):
        """Test uploading a valid .zip archive."""
        machine = db.query(Machine).first()
        assert machine is not None

        # Create a mock file
        file_content = b"PK\x03\x04"  # ZIP file magic bytes
        file = BytesIO(file_content)

        case = _create_case(db, "test_case_zip", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-zip-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test.zip", file, "application/zip")},
            )

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0
        assert len(data["simulations"]) == 1
        assert data["simulations"][0]["execution_id"] == "exec-zip-1"
        assert data["simulations"][0]["case_name"] == "test_case_zip"

    def test_upload_valid_tar_gz_file(self, client, db: Session):
        """Test uploading a valid .tar.gz archive."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"\x1f\x8b\x08"  # GZIP magic bytes
        file = BytesIO(file_content)

        case = _create_case(db, "test_case_targz", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-targz-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test.tar.gz", file, "application/gzip")},
            )

        assert res.status_code == 201
        assert res.json()["simulations"][0]["execution_id"] == "exec-targz-1"

    def test_upload_invalid_file_extension(self, client, db: Session):
        """Test that invalid file extensions are rejected."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"some content"
        file = BytesIO(file_content)

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": machine.name},
            files={"file": ("test.txt", file, "text/plain")},
        )

        assert res.status_code == 400
        assert "File must be a .zip, .tar.gz, or .tgz archive" in res.json()["detail"]

    def test_upload_returns_404_when_machine_not_found(self, client):
        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": "does-not-exist-machine"},
            files={"file": ("test.zip", file, "application/zip")},
        )

        assert res.status_code == 404
        assert res.json()["detail"] == "Machine 'does-not-exist-machine' not found."

    def test_upload_creates_audit_record_with_sha256(self, client, db: Session):
        """Test that upload creates audit record with SHA256 hash."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04test content"
        file = BytesIO(file_content)

        case = _create_case(db, "test_case_sha256", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-sha256-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_upload.zip", file, "application/zip")},
            )

        assert res.status_code == 201

        # Verify audit record with SHA256
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_upload.zip")
            .first()
        )

        assert ingestion is not None
        assert str(ingestion.source_type) == "browser_upload"
        assert ingestion.status == "success"
        assert ingestion.archive_sha256 is not None
        assert len(ingestion.archive_sha256) == 64  # SHA256 hex length

    def test_upload_rejects_partial_ingestion_results(self, client, db: Session):
        """Upload endpoint should fail instead of persisting partial ingestion results."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        case = _create_case(db, "test_case_partial", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-partial-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]
        mock_errors = [{"file": "sim2.json", "error": "Invalid format"}]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=mock_errors,
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_partial.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": mock_errors,
        }

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_partial.zip")
            .first()
        )
        assert ingestion is None

    def test_upload_rejects_failed_ingestion_results(self, client, db: Session):
        """Upload endpoint should fail instead of persisting failed ingestion results."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing required field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[], created_count=0, duplicate_count=0, errors=mock_errors
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_failed.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": mock_errors,
        }

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_failed.zip")
            .first()
        )
        assert ingestion is None

    def test_upload_without_filename(self, client, db: Session):
        """Test that upload without filename is rejected."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        # Create a mock UploadFile with no filename
        mock_file = MagicMock()
        mock_file.filename = None
        mock_file.file = file

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": machine.name},
            files={"file": ("", file, "application/zip")},
        )

        # Should either reject or handle gracefully
        assert res.status_code in [400, 422]

    def test_upload_persists_remote_hpc_path_artifacts_as_metadata(
        self, client, db: Session
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        file = BytesIO(b"PK\x03\x04")
        execution_id = "1083010.260305-120010"
        parsed_simulations = [
            ParsedSimulation(
                execution_dir="/tmp/uploaded/archive/case/1083010.260305-120010",
                execution_id=execution_id,
                case_name="v3.LR.historical_0121",
                case_group=None,
                machine=machine.name,
                hpc_username="ac.golaz",
                compset="FHIST",
                compset_alias="test_alias",
                grid_name="grid1",
                grid_resolution="0.9x1.25",
                campaign="v3.LR.historical",
                experiment_type="historical",
                initialization_type="branch",
                simulation_start_date="2020-01-01",
                simulation_end_date=None,
                run_start_date=None,
                run_end_date=None,
                compiler="gnu",
                git_repository_url="https://github.com/E3SM-Project/E3SM.git",
                git_branch="main",
                git_tag="v3",
                git_commit_hash="abc123",
                status="completed",
                output_path="/lcrc/group/e3sm/run",
                archive_path="/lcrc/group/e3sm/archive",
                case_root="/lcrc/group/e3sm/case_scripts",
                postprocessing_script="/global/homes/a/ac.golaz/post.sh --flag value",
            )
        ]

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(parsed_simulations, 0),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("remote-paths.zip", file, "application/zip")},
            )

        assert res.status_code == 201
        simulation = (
            db.query(Simulation).filter(Simulation.execution_id == execution_id).first()
        )
        assert simulation is not None
        by_kind = {artifact.kind: artifact.uri for artifact in simulation.artifacts}
        assert by_kind[ArtifactKind.OUTPUT] == "/lcrc/group/e3sm/run"
        assert by_kind[ArtifactKind.ARCHIVE] == "/lcrc/group/e3sm/archive"
        assert (
            by_kind[ArtifactKind.RUN_SCRIPT]
            == "/lcrc/group/e3sm/case_scripts/.case.run"
        )
        assert (
            by_kind[ArtifactKind.POSTPROCESS_SCRIPT]
            == "/global/homes/a/ac.golaz/post.sh"
        )

    def test_path_endpoint_handles_lookup_error(self, client, db: Session, tmp_path):
        """Test that LookupError is handled with 400 response."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "lookup_error.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found"

    def test_path_endpoint_persists_remote_hpc_path_artifacts_as_metadata(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "remote-paths.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}
        execution_id = "1083011.260305-120011"
        parsed_simulations = [
            ParsedSimulation(
                execution_dir=str(tmp_path / "archive" / "case" / execution_id),
                execution_id=execution_id,
                case_name="v3.LR.historical_0121",
                case_group=None,
                machine=machine.name,
                hpc_username="ac.golaz",
                compset="FHIST",
                compset_alias="test_alias",
                grid_name="grid1",
                grid_resolution="0.9x1.25",
                campaign="v3.LR.historical",
                experiment_type="historical",
                initialization_type="branch",
                simulation_start_date="2020-01-01",
                simulation_end_date=None,
                run_start_date=None,
                run_end_date=None,
                compiler="gnu",
                git_repository_url="https://github.com/E3SM-Project/E3SM.git",
                git_branch="main",
                git_tag="v3",
                git_commit_hash="abc123",
                status="completed",
                output_path="/pscratch/sd/a/ac.golaz/run",
                archive_path="/pscratch/sd/a/ac.golaz/archive",
                case_root="/pscratch/sd/a/ac.golaz/case_scripts",
                postprocessing_script="/pscratch/sd/a/ac.golaz/post.sh --flag value",
            )
        ]

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(parsed_simulations, 0),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        simulation = (
            db.query(Simulation).filter(Simulation.execution_id == execution_id).first()
        )
        assert simulation is not None
        by_kind = {artifact.kind: artifact.uri for artifact in simulation.artifacts}
        assert by_kind[ArtifactKind.OUTPUT] == "/pscratch/sd/a/ac.golaz/run"
        assert by_kind[ArtifactKind.ARCHIVE] == "/pscratch/sd/a/ac.golaz/archive"
        assert (
            by_kind[ArtifactKind.RUN_SCRIPT]
            == "/pscratch/sd/a/ac.golaz/case_scripts/.case.run"
        )
        assert (
            by_kind[ArtifactKind.POSTPROCESS_SCRIPT]
            == "/pscratch/sd/a/ac.golaz/post.sh"
        )

    def test_path_endpoint_handles_generic_exception(
        self, client, db: Session, tmp_path
    ):
        """Test that generic exceptions are handled with 500 response."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "exception.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("Unexpected error"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 500
        assert res.json()["detail"] == "Unexpected error"

    def test_path_endpoint_failed_status_no_simulations_with_errors(
        self, client, db: Session, tmp_path
    ):
        """Test that failed status is set when no simulations are created but errors exist."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "failed_status.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[], created_count=0, duplicate_count=0, errors=mock_errors
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        # Verify failed status in audit record
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert ingestion.status == "failed"
        assert ingestion.created_count == 0
        assert ingestion.error_count == 2

    def test_path_endpoint_does_not_persist_empty_case_on_ingest_error(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "orphan_case.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        parsed_simulation = ParsedSimulation(
            execution_dir="/path/to/1081175.251218-200942",
            execution_id="1081175.251218-200942",
            case_name="orphan_case_endpoint",
            case_group=None,
            machine=machine.name,
            hpc_username=None,
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid",
            grid_resolution="0.9x1.25",
            campaign=None,
            experiment_type=None,
            initialization_type="test",
            simulation_start_date=None,
            simulation_end_date=None,
            run_start_date=None,
            run_end_date=None,
            compiler=None,
            git_repository_url=None,
            git_branch=None,
            git_tag=None,
            git_commit_hash=None,
            status=None,
        )

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=([parsed_simulation], 0),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        assert res.json()["created_count"] == 0
        assert len(res.json()["errors"]) == 1

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )
        assert ingestion is not None
        assert ingestion.status == "failed"
        assert (
            db.query(Case).filter(Case.name == "orphan_case_endpoint").first() is None
        )

    def test_save_uploaded_file_rejects_large_files(self, tmp_path: Path):
        file_content = b"x" * (51 * 1024 * 1024)  # 51MB
        upload_file = UploadFile(file=BytesIO(file_content), filename="large_file.zip")

        with pytest.raises(HTTPException) as exc_info:
            _save_uploaded_file_and_hash(upload_file, tmp_path / "large_file.zip")

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "File too large"

    def test_upload_returns_structured_validation_errors(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None

        file = BytesIO(b"PK\x03\x04")
        validation_errors = [
            {
                "code": "missing_required_file",
                "execution_dir": "/tmp/archive/1.0-0",
                "file_spec": "env_case.xml..*.gz",
                "location": "casedocs/",
                "message": "Missing required 'env_case.xml..*.gz' in casedocs/ for '/tmp/archive/1.0-0'.",
            }
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ArchiveValidationError(validation_errors),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("invalid.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": validation_errors,
        }

    def test_upload_handles_lookup_error(self, client, db: Session):
        """Test that LookupError in upload is handled with 400 response."""

        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"lookup_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found in upload"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": (unique_filename, file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found in upload"

    def test_upload_handles_generic_exception(self, client, db: Session):
        """Test that generic exceptions in upload are handled with 500 response."""

        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"generic_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("Unexpected upload error"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": (unique_filename, file, "application/zip")},
            )

        assert res.status_code == 500
        assert res.json()["detail"] == "Unexpected upload error"

    def test_persist_simulations_with_artifacts(self, client, db: Session, tmp_path):
        """Test that simulations with artifacts are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_artifacts.tar.gz"
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = _create_case(db, "test_case_artifacts", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-artifacts-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "artifacts": [
                        {
                            "kind": "output",
                            "uri": "https://example.com/output.tar.gz",
                            "description": "Model output",
                        }
                    ],
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert len(simulation.artifacts) == 1
        assert simulation.artifacts[0].kind == "output"
        assert simulation.artifacts[0].uri == "https://example.com/output.tar.gz"

    def test_persist_simulations_with_links(self, client, db: Session, tmp_path):
        """Test that simulations with external links are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "archive_with_links.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = _create_case(db, "test_case_links", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-links-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "links": [
                        {
                            "kind": "diagnostic",
                            "url": "https://example.com/diagnostics",
                            "label": "Diagnostics Dashboard",
                        }
                    ],
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert len(simulation.links) == 1
        assert simulation.links[0].kind == "diagnostic"
        assert simulation.links[0].url == "https://example.com/diagnostics"

    def test_upload_with_none_filename_in_validation(self, client):
        """Test that upload with file.filename = None is rejected by validation."""

        file_content = b"PK\x03\x04"
        file_obj = BytesIO(file_content)

        # Create a real UploadFile with filename = None
        upload_file = UploadFile(file=file_obj, filename=None)

        with pytest.raises(HTTPException) as exc_info:
            _validate_upload_file(upload_file)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Filename is required"

    def test_persist_simulations_with_git_repository_url(
        self, client, db: Session, tmp_path
    ):
        """Test that simulations with git_repository_url are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_git_url.tar.gz"
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = _create_case(db, "test_case_git_url", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-git-url-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "gitRepositoryUrl": "https://github.com/E3SM-Project/E3SM.git",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert (
            simulation.git_repository_url == "https://github.com/E3SM-Project/E3SM.git"
        )

    def test_persist_simulations_with_hpc_username(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_hpc_username.tar.gz"
        )
        payload = {
            "archive_path": str(archive_path),
            "machine_name": machine.name,
            "hpc_username": "nersc-user",
        }

        case = _create_case(
            db,
            "test_case_hpc_username",
            machine=machine,
            hpc_username="nersc-user",
        )

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-hpc-username-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        persisted_case = db.query(Case).filter(Case.id == simulation.case_id).first()
        assert persisted_case is not None
        assert persisted_case.hpc_username == "nersc-user"

    def test_path_ingestion_uses_request_hpc_username_when_metadata_missing(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_request_hpc_username.tar.gz"
        )
        payload = {
            "archive_path": str(archive_path),
            "machine_name": machine.name,
            "hpc_username": "fallback-user",
        }
        execution_id = "1083012.260305-120012"
        parsed_simulations = [
            ParsedSimulation(
                execution_dir=str(tmp_path / "archive" / execution_id),
                execution_id=execution_id,
                case_name="request_fallback_case",
                case_group=None,
                machine=machine.name,
                hpc_username=None,
                compset="FHIST",
                compset_alias="test_alias",
                grid_name="grid1",
                grid_resolution="0.9x1.25",
                campaign=None,
                experiment_type=None,
                initialization_type="branch",
                simulation_start_date="2020-01-01",
                simulation_end_date=None,
                run_start_date=None,
                run_end_date=None,
                compiler="gnu",
                git_repository_url=None,
                git_branch=None,
                git_tag=None,
                git_commit_hash=None,
                status="completed",
            )
        ]

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(parsed_simulations, 0),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        assert res.json()["simulations"][0]["case_name"] == "request_fallback_case"

        simulation = (
            db.query(Simulation).filter(Simulation.execution_id == execution_id).first()
        )
        assert simulation is not None

        case = db.query(Case).filter(Case.id == simulation.case_id).first()
        assert case is not None
        assert case.hpc_username == "fallback-user"


class TestIngestFromHpcUploadEndpoint:
    def test_endpoint_returns_403_for_non_admin_user(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None

        app.dependency_overrides[current_active_user] = fake_non_admin_user

        res = client.post(
            f"{API_BASE}/ingestions/from-hpc-upload",
            data={
                "machine_name": machine.name,
                "case_path": "/archive/case_a",
                "processed_execution_ids": "100.1-1",
            },
            files={"file": ("case_a.tar.gz", BytesIO(b"fake"), "application/gzip")},
        )

        assert res.status_code == 403
        assert (
            res.json()["detail"]
            == "Only administrators and service accounts may upload automated HPC archives."
        )

    def test_endpoint_persists_hpc_upload_with_case_path_sha_and_processed_execution_ids(
        self, client, db: Session
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        case = _create_case(db, "test_case_hpc_upload", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-hpc-upload-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-hpc-upload",
                data={
                    "machine_name": machine.name,
                    "case_path": "/archive/case_a",
                    "processed_execution_ids": ["101.1-1", "100.1-1"],
                },
                files={
                    "file": (
                        "case_a.tar.gz",
                        BytesIO(b"case-a-archive"),
                        "application/gzip",
                    )
                },
            )

        assert res.status_code == 201
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "/archive/case_a")
            .first()
        )

        assert ingestion is not None
        assert ingestion.source_type == IngestionSourceType.HPC_UPLOAD
        assert ingestion.archive_sha256 is not None
        assert len(ingestion.archive_sha256) == 64
        assert ingestion.processed_execution_ids == ["100.1-1", "101.1-1"]

    def test_endpoint_allows_partial_and_duplicate_only_results_for_stateful_dedupe(
        self, client, db: Session
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[],
                created_count=0,
                duplicate_count=1,
                errors=[{"execution_dir": "x", "error": "duplicate"}],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-hpc-upload",
                data={
                    "machine_name": machine.name,
                    "case_path": "/archive/case_duplicate",
                    "processed_execution_ids": ["200.1-1"],
                },
                files={
                    "file": (
                        "case_duplicate.tar.gz",
                        BytesIO(b"case-duplicate-archive"),
                        "application/gzip",
                    )
                },
            )

        assert res.status_code == 201
        assert res.json()["duplicate_count"] == 1
        assert res.json()["errors"] == [{"execution_dir": "x", "error": "duplicate"}]

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "/archive/case_duplicate")
            .first()
        )
        assert ingestion is not None
        assert ingestion.source_type == IngestionSourceType.HPC_UPLOAD
        assert ingestion.processed_execution_ids == ["200.1-1"]

    def test_endpoint_rejects_multi_case_uploads(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None

        first_case = _create_case(db, "multi_case_first", machine=machine)
        second_case = _create_case(db, "multi_case_second", machine=machine)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(first_case.id),
                    "executionId": "multi-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                }
            ),
            SimulationCreate.model_validate(
                {
                    "caseId": str(second_case.id),
                    "executionId": "multi-2",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                }
            ),
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=2,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-hpc-upload",
                data={
                    "machine_name": machine.name,
                    "case_path": "/archive/case_multi",
                    "processed_execution_ids": ["300.1-1"],
                },
                files={
                    "file": (
                        "case_multi.tar.gz",
                        BytesIO(b"case-multi-archive"),
                        "application/gzip",
                    )
                },
            )

        assert res.status_code == 400
        assert "must contain exactly one case" in res.json()["detail"]


class TestIngestionApiCoverage:
    def test_run_ingest_archive_handles_validation_error(self, db: Session):
        """Covers ValidationError branch in _run_ingest_archive."""

        class _InvalidSchema(BaseModel):
            value: int

        with pytest.raises(ValidationError) as validation_exc:
            _InvalidSchema.model_validate({"value": "not-an-int"})

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=validation_exc.value,
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run_ingest_archive("/tmp/archive.tar.gz", "/tmp", db)

        assert exc_info.value.status_code == 400

    def test_run_ingest_archive_forwards_strict_validation_and_hpc_username(
        self, db: Session
    ):
        expected_result = IngestArchiveResult(
            simulations=[],
            created_count=0,
            duplicate_count=0,
            errors=[],
        )

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=expected_result,
        ) as mock_ingest_archive:
            result = _run_ingest_archive(
                "/tmp/archive.tar.gz",
                "/tmp",
                db,
                strict_validation=True,
                hpc_username="request-user",
            )

        assert result == expected_result
        mock_ingest_archive.assert_called_once_with(
            archive_path="/tmp/archive.tar.gz",
            output_dir="/tmp",
            db=db,
            strict_validation=True,
            hpc_username="request-user",
        )

    def test_run_ingest_archive_handles_archive_validation_error(self, db: Session):
        validation_errors = [
            {
                "code": "missing_required_file",
                "execution_dir": "/tmp/archive/1.0-0",
                "file_spec": "CaseStatus..*.gz",
                "location": "archive root",
                "message": "Missing required 'CaseStatus..*.gz' in archive root for '/tmp/archive/1.0-0'.",
            }
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ArchiveValidationError(validation_errors),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run_ingest_archive("/tmp/archive.tar.gz", "/tmp", db)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == {
            "message": "Archive validation failed.",
            "errors": validation_errors,
        }

    def test_ingest_from_upload_defensive_filename_none_branch(
        self, db: Session, normal_user_sync: dict
    ):
        """Covers defensive filename None branch in ingest_from_upload."""
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        upload_file = UploadFile(file=BytesIO(b"archive-bytes"), filename=None)

        with patch(
            "app.features.ingestion.api._validate_upload_file", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                ingest_from_upload(
                    file=upload_file,
                    machine_name=machine.name,
                    db=db,
                    user=user,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Filename is required"

    def test_ingest_from_upload_ignores_file_close_errors(
        self, db: Session, normal_user_sync: dict
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        raw_file = MagicMock()
        raw_file.close.side_effect = RuntimeError("close failed")
        upload_file = UploadFile(file=raw_file, filename="archive.zip")
        response = MagicMock()

        with (
            patch(
                "app.features.ingestion.api._validate_upload_file", return_value=None
            ),
            patch(
                "app.features.ingestion.api._save_uploaded_file_and_hash",
                return_value="deadbeef",
            ),
            patch(
                "app.features.ingestion.api._run_ingest_archive",
                return_value=IngestArchiveResult(
                    simulations=[],
                    created_count=0,
                    duplicate_count=0,
                    errors=[],
                ),
            ),
            patch(
                "app.features.ingestion.api._process_ingestion",
                return_value=response,
            ),
        ):
            result = ingest_from_upload(
                file=upload_file,
                machine_name=machine.name,
                db=db,
                user=user,
            )

        assert result is response
        raw_file.close.assert_called_once_with()

    def test_build_hpc_upload_payload_translates_validation_errors(self):
        with pytest.raises(HTTPException) as exc_info:
            _build_hpc_upload_payload(
                machine_name="perlmutter",
                case_path="   ",
                hpc_username=None,
                processed_execution_ids=None,
            )

        assert exc_info.value.status_code == 422
        assert {error["loc"][-1] for error in exc_info.value.detail} == {
            "case_path",
            "processed_execution_ids",
        }

    def test_ingest_from_hpc_upload_defensive_filename_none_branch(
        self, db: Session, normal_user_sync: dict
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.ADMIN,
        )
        upload_file = UploadFile(file=BytesIO(b"archive-bytes"), filename=None)

        with patch(
            "app.features.ingestion.api._validate_upload_file", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                ingest_from_hpc_upload(
                    file=upload_file,
                    machine_name=machine.name,
                    case_path="/archive/case_a",
                    hpc_username=None,
                    processed_execution_ids=["100.1-1"],
                    db=db,
                    user=user,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Filename is required"

    def test_ingest_from_hpc_upload_ignores_file_close_errors(
        self, db: Session, normal_user_sync: dict
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.SERVICE_ACCOUNT,
        )
        raw_file = MagicMock()
        raw_file.close.side_effect = RuntimeError("close failed")
        upload_file = UploadFile(file=raw_file, filename="archive.tar.gz")
        response = MagicMock()

        with (
            patch(
                "app.features.ingestion.api._validate_upload_file", return_value=None
            ),
            patch(
                "app.features.ingestion.api._save_uploaded_file_and_hash",
                return_value="deadbeef",
            ),
            patch(
                "app.features.ingestion.api._run_ingest_archive",
                return_value=IngestArchiveResult(
                    simulations=[],
                    created_count=0,
                    duplicate_count=0,
                    errors=[],
                ),
            ),
            patch(
                "app.features.ingestion.api._process_ingestion",
                return_value=response,
            ),
        ):
            result = ingest_from_hpc_upload(
                file=upload_file,
                machine_name=machine.name,
                case_path="/archive/case_a",
                hpc_username=None,
                processed_execution_ids=["100.1-1"],
                db=db,
                user=user,
            )

        assert result is response
        raw_file.close.assert_called_once_with()

    def test_validate_archive_path_not_file_or_dir(self, tmp_path):
        """Covers the branch where path exists but is neither file nor dir."""
        archive_path = tmp_path / "special"
        archive_path.touch()

        with (
            patch.object(Path, "is_file", return_value=False),
            patch.object(Path, "is_dir", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _validate_archive_path(archive_path)

        assert exc_info.value.status_code == 400
        assert "must be a file or directory" in exc_info.value.detail
