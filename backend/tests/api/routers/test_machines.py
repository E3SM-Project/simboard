from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routers.machine import create_machine, get_machine, list_machines
from app.db.models.machine import Machine
from app.schemas.machine import MachineCreate


class TestCreateMachine:
    def test_create_machine_success(self, client, db: Session):
        payload = {
            "name": "Machine A",
            "site": "Site A",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Test machine",
        }

        # Test the actual function
        machine_create = MachineCreate(**payload)  # type: ignore
        machine = create_machine(machine_create, db)

        for key in payload:
            assert getattr(machine, key) == payload[key]

        # Test the API endpoint
        payload2 = {
            "name": "Machine F",
            "site": "Site F",
            "architecture": "ARM",
            "scheduler": "Kubernetes",
            "gpu": False,
            "notes": "Another test machine",
        }

        res = client.post("/machines", json=payload2)

        assert res.status_code == 201
        data = res.json()

        for key in payload:
            assert data[key] == payload2[key]

    def test_create_machine_duplicate_name(self, db: Session, client):
        # Seed an existing machine
        db.add(
            Machine(
                name="Machine B",
                site="Site B",
                architecture="x86_64",
                scheduler="PBS",
                gpu=False,
                notes="Existing machine",
            )
        )
        db.commit()

        payload = {
            "name": "Machine B",
            "site": "Site C",
            "architecture": "ARM",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Duplicate machine",
        }

        # Test the actual function
        try:
            machine_create = MachineCreate(**payload)  # type: ignore
            create_machine(machine_create, db)
        except HTTPException as e:
            assert str(e) == "400: Machine with this name already exists"

        # Test the API endpoint
        res = client.post("/machines", json=payload)
        assert res.status_code == 400
        assert res.json()["detail"] == "Machine with this name already exists"


class TestListMachines:
    def test_list_machines(self, db: Session, client):
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

        # Test the actual function
        machines = list_machines(db)
        result = {m.name for m in machines}

        assert result == expected_machines

        # Test the API endpoint
        res = client.get("/machines")
        assert res.status_code == 200
        data = res.json()

        # Don’t rely on DB ordering.
        result_api = {m["name"] for m in data}
        assert result_api == expected_machines


class TestGetMachine:
    def test_get_machine_success(self, db: Session, client):
        expected = Machine(
            name="Machine E",
            site="Site E",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=True,
            notes="Test machine",
        )
        db.add(expected)
        db.commit()
        db.refresh(expected)

        # Test the actual function
        result = get_machine(expected.id, db)
        assert result.name == expected.name
        assert result.notes == expected.notes

        # Test the API endpoint
        res = client.get(f"/machines/{expected.id}")
        assert res.status_code == 200

        result_api = res.json()
        assert result_api["name"] == expected.name
        assert result_api["notes"] == expected.notes

    def test_get_machine_not_found(self, client, db: Session):
        random_id = uuid4()

        # Test the actual function
        try:
            get_machine(random_id, db)
        except HTTPException as e:
            assert str(e) == "404: Machine not found"

        # Test the API endpoint
        res = client.get(f"/machines/{random_id}")
        assert res.status_code == 404
        assert res.json()["detail"] == "Machine not found"
