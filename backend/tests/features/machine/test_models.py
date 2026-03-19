from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.common.models.base import Base
from app.features.machine.models import Machine
from tests.conftest import engine


@pytest.fixture
def machine_create_all_db() -> Generator[Session, None, None]:
    schema_name = f"test_machine_create_all_{uuid4().hex}"

    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        Base.metadata.create_all(
            bind=connection,
            tables=[cast(Table, Machine.__table__)],
        )
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


class TestMachineModelCreateAllSchema:
    def test_create_all_schema_enforces_case_insensitive_uniqueness(
        self, machine_create_all_db: Session
    ) -> None:
        machine_create_all_db.add(
            Machine(
                name="machine constraint",
                site="Site A",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )
        machine_create_all_db.commit()

        machine_create_all_db.add(
            Machine(
                name="MACHINE CONSTRAINT",
                site="Site B",
                architecture="ARM",
                scheduler="PBS",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            machine_create_all_db.commit()

        machine_create_all_db.rollback()

    def test_create_all_schema_enforces_lowercase_machine_names(
        self, machine_create_all_db: Session
    ) -> None:
        machine_create_all_db.add(
            Machine(
                name="Mixed-Case-Machine",
                site="Site Mixed",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            machine_create_all_db.commit()

        machine_create_all_db.rollback()
