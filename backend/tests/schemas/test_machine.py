from datetime import datetime
from uuid import uuid4

from app.features.machine.api import MachineCreate, MachineOut


class TestMachineCreate:
    def test_machine_create_initialization(self):
        # Arrange
        data = {
            "name": "Test Machine",
            "site": "Test Site",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "This is a test machine.",
        }

        # Act
        machine = MachineCreate(**data)  # type: ignore

        # Assert
        assert machine.model_dump() == data

    def test_machine_create_defaults(self):
        # Arrange
        data = {
            "name": "Test Machine",
            "site": "Test Site",
            "architecture": "x86_64",
            "scheduler": "SLURM",
        }

        # Act
        machine = MachineCreate(**data)  # type: ignore

        # Assert
        assert machine.gpu is False and machine.notes is None


class TestMachineOut:
    def test_machine_out_initialization(self):
        # Arrange
        data = {
            "id": uuid4(),
            "name": "Test Machine",
            "site": "Test Site",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "notes": "This is a test machine.",
        }

        # Act
        machine = MachineOut(**data)  # type: ignore

        # Assert
        assert machine.model_dump() == data

    def test_machine_out_optional_notes(self):
        # Arrange
        data = {
            "id": uuid4(),
            "name": "Test Machine",
            "site": "Test Site",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        # Act
        machine = MachineOut(**data)  # type: ignore

        # Assert
        assert machine.notes is None
