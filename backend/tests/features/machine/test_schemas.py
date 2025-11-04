from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.features.machine.schemas import MachineCreate, MachineOut


class TestMachineCreateSchema:
    def test_valid_machine_create_schema(self):
        payload = {
            "name": "Machine A",
            "site": "Site A",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": True,
            "notes": "Test machine",
        }

        machine_create = MachineCreate(**payload)

        for key in payload:
            assert getattr(machine_create, key) == payload[key]

    def test_invalid_machine_create_schema_missing_fields(self):
        payload = {
            "name": "Machine A",
            "site": "Site A",
        }

        try:
            MachineCreate(**payload)
        except ValidationError as e:
            missing_fields = {
                error["loc"][0] for error in e.errors() if error["type"] == "missing"
            }
            expected_missing_fields = {"architecture", "scheduler"}

            assert missing_fields == expected_missing_fields

    def test_invalid_machine_create_schema_wrong_field_type(self):
        payload = {
            "name": "Machine A",
            "site": "Site A",
            "architecture": "x86_64",
            "scheduler": "SLURM",
            "gpu": "not_a_boolean",  # Invalid type
            "notes": "Test machine",
        }

        try:
            MachineCreate(**payload)
        except ValidationError as e:
            assert "Input should be a valid boolean" in str(e)


class TestMachineOutSchema:
    def test_valid_machine_out_schema(self):
        payload = {
            "id": uuid4(),
            "name": "Machine B",
            "site": "Site B",
            "architecture": "arm64",
            "scheduler": "PBS",
            "gpu": False,
            "notes": "Another test machine",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        machine_out = MachineOut(**payload)

        for key in payload:
            assert getattr(machine_out, key) == payload[key]

    def test_invalid_machine_out_schema_missing_fields(self):
        payload = {
            "id": uuid4(),
            "name": "Machine B",
            "site": "Site B",
        }

        try:
            MachineOut(**payload)
        except ValidationError as e:
            missing_fields = {
                error["loc"][0] for error in e.errors() if error["type"] == "missing"
            }
            expected_missing_fields = {
                "architecture",
                "scheduler",
                "createdAt",
                "updatedAt",
            }
            assert missing_fields == expected_missing_fields

    def test_invalid_machine_out_schema_wrong_field_type(self):
        payload = {
            "id": "not_a_uuid",  # Invalid type
            "name": "Machine B",
            "site": "Site B",
            "architecture": "arm64",
            "scheduler": "PBS",
            "gpu": False,
            "notes": "Another test machine",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        try:
            MachineOut(**payload)
        except ValidationError as e:
            assert "Input should be a valid UUID" in str(e)
