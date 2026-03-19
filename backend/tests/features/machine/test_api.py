from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.machine.api import create_machine, get_machine, list_machines
from app.features.machine.models import Machine
from app.features.machine.schemas import MachineCreate


class TestCreateMachine:
    def test_function_succeeds_with_valid_payload(self, db: Session):
        payload = {
            "name": "Machine A",
            "site": "Site A",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Test machine",
        }

        machine_create = MachineCreate(**payload)
        machine = create_machine(machine_create, db)

        assert machine.name == "machine a"
        for key in payload:
            if key != "name":
                assert getattr(machine, key) == payload[key]

    def test_endpoint_succeeds_with_valid_payload(self, client):
        payload = {
            "name": "Machine F",
            "site": "Site F",
            "architecture": "ARM",
            "scheduler": "Kubernetes",
            "gpu": False,
            "notes": "Another test machine",
        }

        res = client.post(f"{API_BASE}/machines", json=payload)

        assert res.status_code == 201
        data = res.json()

        assert data["name"] == "machine f"
        for key in payload:
            if key != "name":
                assert data[key] == payload[key]

    def test_function_does_not_expand_aliases_on_write(self, db: Session):
        payload = {
            "name": "pm",
            "site": "Site Alias",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": False,
            "notes": "Alias should not expand on write",
        }

        machine_create = MachineCreate(**payload)
        machine = create_machine(machine_create, db)

        assert machine.name == "pm"

    def test_endpoint_does_not_expand_aliases_on_write(self, client):
        payload = {
            "name": "pm",
            "site": "Site Alias",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": False,
            "notes": "Alias should not expand on write",
        }

        res = client.post(f"{API_BASE}/machines", json=payload)

        assert res.status_code == 201
        assert res.json()["name"] == "pm"

    def test_function_raises_error_for_duplicate_name_(self, db: Session):
        db.add(
            Machine(
                name="machine b",
                site="Site B",
                architecture="x86_64",
                scheduler="PBS",
                gpu=False,
                notes="Existing machine",
            )
        )
        db.commit()

        payload = {
            "name": "MACHINE B",
            "site": "Site C",
            "architecture": "ARM",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Duplicate machine",
        }

        try:
            machine_create = MachineCreate(**payload)
            create_machine(machine_create, db)
        except HTTPException as e:
            assert str(e) == "400: Machine with this name already exists"

    def test_endpoint_raises_400_for_duplicate_name(self, client, db: Session):
        db.add(
            Machine(
                name="machine b",
                site="Site B",
                architecture="x86_64",
                scheduler="PBS",
                gpu=False,
                notes="Existing machine",
            )
        )
        db.commit()

        payload = {
            "name": "MACHINE B",
            "site": "Site C",
            "architecture": "ARM",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Duplicate machine",
        }

        res = client.post(f"{API_BASE}/machines", json=payload)
        assert res.status_code == 400
        assert res.json()["detail"] == "Machine with this name already exists"

    def test_database_enforces_case_insensitive_machine_uniqueness(
        self, db: Session
    ) -> None:
        db.add(
            Machine(
                name="machine constraint",
                site="Site A",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )
        db.commit()

        db.add(
            Machine(
                name="MACHINE CONSTRAINT",
                site="Site B",
                architecture="ARM",
                scheduler="PBS",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    def test_database_enforces_lowercase_machine_names(self, db: Session) -> None:
        db.add(
            Machine(
                name="Mixed-Case-Machine",
                site="Site Mixed",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    def test_database_uses_lowercase_unique_index_for_machine_names(
        self, db: Session
    ) -> None:
        index_rows = db.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'machines'
                ORDER BY indexname
                """
            )
        ).all()

        indexes = {row[0]: row[1] for row in index_rows}

        assert "ix_machines_name" not in indexes
        assert "uq_machines_name_lower" in indexes
        assert "UNIQUE INDEX" in indexes["uq_machines_name_lower"]
        assert "lower(" in indexes["uq_machines_name_lower"]

        constraint_rows = db.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'public' AND t.relname = 'machines'
                ORDER BY conname
                """
            )
        ).all()

        constraints = {row[0]: row[1] for row in constraint_rows}

        lowercase_constraint = next(
            (
                constraint_def
                for constraint_name, constraint_def in constraints.items()
                if constraint_name.endswith("ck_machines_name_lowercase")
            ),
            None,
        )

        assert lowercase_constraint is not None
        assert "CHECK" in lowercase_constraint
        assert "lower" in lowercase_constraint


class TestListMachines:
    def test_function_successfully_list_machines(self, db: Session):
        expected_machines = {
            "aurora",
            "frontier",
            "anvil",
            "polaris",
            "andes",
            "perlmutter",
            "compy",
            "chrysalis",
        }

        machines = list_machines(db)
        result = {m.name for m in machines}

        assert result == expected_machines

    def test_endpoint_successfully_list_machines(self, client):
        expected_machines = {
            "aurora",
            "frontier",
            "anvil",
            "polaris",
            "andes",
            "perlmutter",
            "compy",
            "chrysalis",
        }

        res = client.get(f"{API_BASE}/machines")
        assert res.status_code == 200
        data = res.json()

        result_endpoint = {m["name"] for m in data}
        assert result_endpoint == expected_machines


class TestGetMachine:
    def test_function_successfully_gets_machine(self, db: Session):
        expected = Machine(
            name="machine e",
            site="Site E",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=True,
            notes="Test machine",
        )
        db.add(expected)
        db.commit()
        db.refresh(expected)

        result = get_machine(expected.id, db)
        assert result.name == expected.name
        assert result.notes == expected.notes

    def test_endpoint_successfully_get_machine(self, client, db: Session):
        expected = Machine(
            name="machine e",
            site="Site E",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=True,
            notes="Test machine",
        )
        db.add(expected)
        db.commit()
        db.refresh(expected)

        res = client.get(f"{API_BASE}/machines/{expected.id}")
        assert res.status_code == 200

        result_endpoint = res.json()
        assert result_endpoint["name"] == expected.name
        assert result_endpoint["notes"] == expected.notes

    def test_function_raises_error_if_machine_not_found(self, db: Session):
        random_id = uuid4()

        try:
            get_machine(random_id, db)
        except HTTPException as e:
            assert str(e) == "404: Machine not found"

    def test_endpoint_raises_404_if_machine_not_found(self, client):
        random_id = uuid4()

        res = client.get(f"{API_BASE}/machines/{random_id}")
        assert res.status_code == 404
        assert res.json()["detail"] == "Machine not found"
