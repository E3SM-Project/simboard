from collections.abc import Generator
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.common.models.base import Base
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.enums import (
    ExternalLinkKind,
    SimulationStatus,
    SimulationType,
)
from app.features.simulation.models import Case, ExternalLink, Simulation
from app.features.user.models import User
from tests.conftest import engine


@pytest.fixture
def simulation_create_all_db() -> Generator[Session, None, None]:
    schema_name = f"test_simulation_create_all_{uuid4().hex}"

    tables = [
        cast(Table, User.__table__),
        cast(Table, Machine.__table__),
        cast(Table, Ingestion.__table__),
        cast(Table, Case.__table__),
        cast(Table, Simulation.__table__),
    ]

    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        Base.metadata.create_all(bind=connection, tables=tables)
        connection.commit()

        session = sessionmaker(
            bind=connection,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )()

        try:
            yield session
        finally:
            session.close()
            connection.execute(text("RESET search_path"))
            connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
            connection.commit()


def _create_machine(db: Session) -> Machine:
    machine = Machine(
        name=f"machine-{datetime.now(timezone.utc).timestamp()}",
        site="NERSC",
        architecture="x86_64",
        scheduler="SLURM",
        gpu=False,
    )
    db.add(machine)
    db.flush()
    return machine


def _create_case(
    db: Session,
    name: str = "external-link-case",
    *,
    machine: Machine | None = None,
    hpc_username: str = "test-user",
) -> Case:
    resolved_machine = machine or _create_machine(db)
    case = Case(
        name=name,
        machine_id=resolved_machine.id,
        hpc_username=hpc_username,
    )
    db.add(case)
    db.flush()
    return case


def _create_ingestion(
    db: Session, *, machine_id: UUID, user_id: UUID, source_reference: str
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


def _create_dependencies(session: Session) -> tuple[User, Machine, Ingestion]:
    user = User(email="simulation-model@example.com", is_active=True, is_verified=True)
    machine = Machine(
        name="simulation-model-machine",
        site="Test Site",
        architecture="x86_64",
        scheduler="SLURM",
        gpu=False,
    )
    session.add_all([user, machine])
    session.flush()

    ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="simulation-model-test",
        machine_id=machine.id,
        triggered_by=user.id,
        status=IngestionStatus.SUCCESS,
        created_count=0,
        duplicate_count=0,
        error_count=0,
    )
    session.add(ingestion)
    session.flush()

    return user, machine, ingestion


def _create_simulation(
    db: Session,
    *,
    case_id: UUID,
    ingestion_id: UUID,
    user_id: UUID,
    execution_id: str,
) -> Simulation:
    simulation = Simulation(
        case_id=case_id,
        execution_id=execution_id,
        compset="AQUAPLANET",
        compset_alias="QPC4",
        grid_name="f19_f19",
        grid_resolution="1.9x2.5",
        simulation_type=SimulationType.EXPERIMENTAL,
        status=SimulationStatus.CREATED,
        initialization_type="startup",
        simulation_start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        created_by=user_id,
        last_updated_by=user_id,
        ingestion_id=ingestion_id,
        extra={},
    )
    db.add(simulation)
    db.flush()
    return simulation


class TestSimulationModelCreateAllSchema:
    def test_create_all_schema_enforces_case_scoped_execution_uniqueness(
        self, simulation_create_all_db: Session
    ) -> None:
        user, machine, ingestion = _create_dependencies(simulation_create_all_db)

        case_one = _create_case(
            simulation_create_all_db,
            "case-one",
            machine=machine,
            hpc_username="schema-user",
        )
        case_two = _create_case(
            simulation_create_all_db,
            "case-two",
            machine=machine,
            hpc_username="schema-user",
        )

        _create_simulation(
            simulation_create_all_db,
            case_id=case_one.id,
            ingestion_id=ingestion.id,
            user_id=user.id,
            execution_id="shared-exec",
        )
        simulation_create_all_db.commit()

        _create_simulation(
            simulation_create_all_db,
            case_id=case_two.id,
            ingestion_id=ingestion.id,
            user_id=user.id,
            execution_id="shared-exec",
        )
        simulation_create_all_db.commit()

        _create_simulation(
            simulation_create_all_db,
            case_id=case_one.id,
            ingestion_id=ingestion.id,
            user_id=user.id,
            execution_id="shared-exec",
        )

        with pytest.raises(IntegrityError):
            simulation_create_all_db.commit()

        simulation_create_all_db.rollback()


class TestExternalLinkOwnership:
    def test_simulation_owned_external_link_is_valid(
        self, db: Session, normal_user_sync
    ) -> None:
        case = _create_case(db, "simulation-owned-case")
        machine = _create_machine(db)
        ingestion = _create_ingestion(
            db,
            machine_id=machine.id,
            user_id=normal_user_sync["id"],
            source_reference="simulation-owned-external-link",
        )
        simulation = _create_simulation(
            db,
            case_id=case.id,
            ingestion_id=ingestion.id,
            user_id=normal_user_sync["id"],
            execution_id="simulation-owned-exec",
        )

        link = ExternalLink(
            simulation_id=simulation.id,
            kind=ExternalLinkKind.DIAGNOSTIC,
            url="https://example.com/sim-owned",
            label="Simulation-owned",
        )
        db.add(link)
        db.commit()
        db.refresh(simulation)

        assert simulation.links[0].id == link.id

    def test_case_owned_external_link_is_valid(
        self, db: Session, normal_user_sync
    ) -> None:
        case = _create_case(db, "case-owned-case")
        machine = _create_machine(db)
        _create_ingestion(
            db,
            machine_id=machine.id,
            user_id=normal_user_sync["id"],
            source_reference="case-owned-external-link",
        )

        link = ExternalLink(
            case_id=case.id,
            kind=ExternalLinkKind.DIAGNOSTIC,
            url="https://example.com/case-owned",
            label="Case-owned",
        )
        db.add(link)
        db.commit()
        db.refresh(case)

        assert case.links[0].id == link.id

    def test_ownerless_external_link_is_invalid(self, db: Session) -> None:
        db.add(
            ExternalLink(
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/ownerless",
                label="Ownerless",
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    def test_dual_owned_external_link_is_invalid(
        self, db: Session, normal_user_sync
    ) -> None:
        case = _create_case(db, "dual-owned-case")
        machine = _create_machine(db)
        ingestion = _create_ingestion(
            db,
            machine_id=machine.id,
            user_id=normal_user_sync["id"],
            source_reference="dual-owned-external-link",
        )
        simulation = _create_simulation(
            db,
            case_id=case.id,
            ingestion_id=ingestion.id,
            user_id=normal_user_sync["id"],
            execution_id="dual-owned-exec",
        )

        db.add(
            ExternalLink(
                simulation_id=simulation.id,
                case_id=case.id,
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/dual-owned",
                label="Dual-owned",
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    def test_duplicate_case_owned_diagnostic_link_is_invalid(self, db: Session) -> None:
        case = _create_case(db, "duplicate-case-link-case")

        db.add_all(
            [
                ExternalLink(
                    case_id=case.id,
                    kind=ExternalLinkKind.DIAGNOSTIC,
                    url="https://example.com/duplicate-case-link",
                    label="First",
                ),
                ExternalLink(
                    case_id=case.id,
                    kind=ExternalLinkKind.DIAGNOSTIC,
                    url="https://example.com/duplicate-case-link",
                    label="Second",
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()
