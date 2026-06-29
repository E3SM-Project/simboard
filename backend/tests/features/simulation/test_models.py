from collections.abc import Generator
from datetime import datetime
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.common.models.base import Base
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.enums import SimulationStatus, SimulationType
from app.features.simulation.models import Case, Simulation
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


def _build_simulation(
    *,
    case_id,
    execution_id: str,
    machine_id,
    user_id,
    ingestion_id,
) -> Simulation:
    return Simulation(
        case_id=case_id,
        execution_id=execution_id,
        compset="FHIST",
        compset_alias="FHIST_f09_fe",
        grid_name="grid",
        grid_resolution="0.9x1.25",
        initialization_type="startup",
        simulation_type=SimulationType.UNKNOWN,
        status=SimulationStatus.CREATED,
        machine_id=machine_id,
        simulation_start_date=datetime(2020, 1, 1),
        created_by=user_id,
        last_updated_by=user_id,
        ingestion_id=ingestion_id,
    )


class TestSimulationModelCreateAllSchema:
    def test_create_all_schema_enforces_case_scoped_execution_uniqueness(
        self, simulation_create_all_db: Session
    ) -> None:
        user, machine, ingestion = _create_dependencies(simulation_create_all_db)

        case_one = Case(name="case-one")
        case_two = Case(name="case-two")
        simulation_create_all_db.add_all([case_one, case_two])
        simulation_create_all_db.flush()

        simulation_create_all_db.add(
            _build_simulation(
                case_id=case_one.id,
                execution_id="shared-exec",
                machine_id=machine.id,
                user_id=user.id,
                ingestion_id=ingestion.id,
            )
        )
        simulation_create_all_db.commit()

        simulation_create_all_db.add(
            _build_simulation(
                case_id=case_two.id,
                execution_id="shared-exec",
                machine_id=machine.id,
                user_id=user.id,
                ingestion_id=ingestion.id,
            )
        )
        simulation_create_all_db.commit()

        simulation_create_all_db.add(
            _build_simulation(
                case_id=case_one.id,
                execution_id="shared-exec",
                machine_id=machine.id,
                user_id=user.id,
                ingestion_id=ingestion.id,
            )
        )

        with pytest.raises(IntegrityError):
            simulation_create_all_db.commit()

        simulation_create_all_db.rollback()
