from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

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

        for key in payload:
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

        res = client.post("/machines", json=payload)

        assert res.status_code == 201
        data = res.json()

        for key in payload:
            assert data[key] == payload[key]

    def test_function_raises_error_for_duplicate_name_(self, db: Session):
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

        try:
            machine_create = MachineCreate(**payload)
            create_machine(machine_create, db)
        except HTTPException as e:
            assert str(e) == "400: Machine with this name already exists"

    def test_endpoint_raises_400_for_duplicate_name(self, client, db: Session):
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

        res = client.post("/machines", json=payload)
        assert res.status_code == 400
        assert res.json()["detail"] == "Machine with this name already exists"


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

        res = client.get("/machines")
        assert res.status_code == 200
        data = res.json()

        result_endpoint = {m["name"] for m in data}
        assert result_endpoint == expected_machines


class TestGetMachine:
    def test_function_successfully_gets_machine(self, db: Session):
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

        result = get_machine(expected.id, db)
        assert result.name == expected.name
        assert result.notes == expected.notes

    def test_endpoint_successfully_get_machine(self, client, db: Session):
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

        res = client.get(f"/machines/{expected.id}")
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

        res = client.get(f"/machines/{random_id}")
        assert res.status_code == 404
        assert res.json()["detail"] == "Machine not found"
