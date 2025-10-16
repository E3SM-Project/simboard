from datetime import datetime
from uuid import uuid4

from pydantic import AnyUrl, HttpUrl

from app.schemas.artifact import ArtifactKind, ArtifactOut
from app.schemas.link import ExternalLinkKind, ExternalLinkOut
from app.schemas.machine import MachineOut
from app.schemas.simulation import SimulationCreate, SimulationOut
from app.schemas.utils import to_snake_case


class TestSimulationCreate:
    def test_simulation_create_required_fields(self):
        payload = {
            "name": "Test Simulation",
            "caseName": "test_case",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "control",
            "status": "new",
            "machineId": uuid4(),
            "simulationStartDate": datetime(2023, 1, 1, 0, 0, 0),
        }

        simulation_create = SimulationCreate(**payload)  # type: ignore
        for key, value in payload.items():
            snake_case_key = to_snake_case(key)
            assert getattr(simulation_create, snake_case_key) == value

    def test_simulation_create_optional_fields(self):
        payload = {
            "name": "Test Simulation",
            "caseName": "test_case",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "control",
            "status": "new",
            "machineId": uuid4(),
            "simulationStartDate": datetime(2023, 1, 1, 0, 0, 0),
            "gitTag": "v1.0",
            "gitCommitHash": "abc123",
            "parentSimulationId": uuid4(),
            "campaignId": "campaign1",
            "experimentTypeId": "exp1",
            "groupName": "group1",
            "simulationEndDate": datetime(2023, 12, 31, 0, 0, 0),
            "runStartDate": datetime(2023, 1, 1, 0, 0, 0),
            "runEndDate": datetime(2023, 12, 31, 0, 0, 0),
            "compiler": "gcc",
            "notesMarkdown": "Some notes",
            "knownIssues": "No known issues",
            "gitBranch": "main",
            "gitRepositoryUrl": HttpUrl("http://example.com/repo"),
            "createdBy": "user1",
            "extra": {"key": "value"},
            "artifacts": [
                {
                    "kind": "output",
                    "uri": AnyUrl("http://example.com/artifact1"),
                    "label": "artifact1",
                }
            ],
            "links": [
                {
                    "kind": "diagnostic",
                    "url": HttpUrl("http://example.com/link1"),
                    "label": "link1",
                }
            ],
        }

        simulation_create = SimulationCreate(**payload)  # type: ignore
        for key, value in payload.items():
            snake_case_key = to_snake_case(key)

            if snake_case_key in ["artifacts", "links"]:
                assert len(getattr(simulation_create, snake_case_key)) == len(value)  # type: ignore
                for i, item in enumerate(value):  # type: ignore
                    for attr, attr_value in item.items():
                        assert (
                            getattr(getattr(simulation_create, snake_case_key)[i], attr)
                            == attr_value
                        )
            else:
                assert getattr(simulation_create, snake_case_key) == value


class TestSimulationOut:
    def test_simulation_out_required_fields(self):
        # Arrange: Define the required fields
        fields = {
            "id": uuid4(),
            "name": "Test Simulation",
            "case_name": "test_case",
            "compset": "AQUAPLANET",
            "compset_alias": "QPC4",
            "grid_name": "f19_f19",
            "grid_resolution": "1.9x2.5",
            "initialization_type": "startup",
            "simulation_type": "control",
            "status": "new",
            "machine_id": uuid4(),
            "simulation_start_date": datetime(2023, 1, 1, 0, 0, 0),
            "created_at": datetime(2023, 1, 1, 0, 0, 0),
            "updated_at": datetime(2023, 1, 2, 0, 0, 0),
            "machine": MachineOut(
                id=uuid4(),
                name="Machine A",
                site="Data Center 1",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=True,
                notes="High-performance computing machine",
                created_at=datetime(2023, 1, 1, 0, 0, 0),
                updated_at=datetime(2023, 1, 2, 0, 0, 0),
            ),
        }

        # Act: Create a SimulationOut instance
        simulation_out = SimulationOut(**fields)  # type: ignore

        # Assert: Validate all fields
        for key, value in fields.items():
            assert getattr(simulation_out, key) == value, (
                f"Field '{key}' does not match the expected value."
            )

        # Assert: Validate optional fields are set to their defaults
        optional_fields = [
            "parent_simulation_id",
            "campaign_id",
            "experiment_type_id",
            "group_name",
            "simulation_end_date",
            "run_start_date",
            "run_end_date",
            "compiler",
            "notes_markdown",
            "known_issues",
            "git_repository_url",
            "git_branch",
            "git_tag",
            "git_commit_hash",
            "created_by",
            "last_updated_by",
        ]
        for field in optional_fields:
            assert getattr(simulation_out, field) is None, (
                f"Optional field '{field}' is not None by default."
            )

        # Assert: Validate default values for list fields
        assert simulation_out.artifacts == [], (
            "Field 'artifacts' is not an empty list by default."
        )
        assert simulation_out.links == [], (
            "Field 'links' is not an empty list by default."
        )

    def test_simulation_out_optional_fields(self):
        required_fields = {
            "id": uuid4(),
            "name": "Test Simulation",
            "case_name": "test_case",
            "compset": "AQUAPLANET",
            "compset_alias": "QPC4",
            "grid_name": "f19_f19",
            "grid_resolution": "1.9x2.5",
            "initialization_type": "startup",
            "simulation_type": "control",
            "status": "new",
            "machine_id": uuid4(),
            "simulation_start_date": datetime(2023, 1, 1, 0, 0, 0),
            "created_at": datetime(2023, 1, 1, 0, 0, 0),
            "updated_at": datetime(2023, 1, 2, 0, 0, 0),
            "machine": MachineOut(
                id=uuid4(),
                name="Machine A",
                site="Data Center 1",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=True,
                notes="High-performance computing machine",
                created_at=datetime(2023, 1, 1, 0, 0, 0),
                updated_at=datetime(2023, 1, 2, 0, 0, 0),
            ),
        }

        optional_fields = {
            "parent_simulation_id": uuid4(),
            "campaign_id": "campaign1",
            "experiment_type_id": "exp1",
            "group_name": "group1",
            "simulation_end_date": datetime(2023, 12, 31, 0, 0, 0),
            "run_start_date": datetime(2023, 1, 1, 0, 0, 0),
            "run_end_date": datetime(2023, 12, 31, 0, 0, 0),
            "compiler": "gcc",
            "notes_markdown": "Some notes",
            "known_issues": "No known issues",
            "git_repository_url": HttpUrl("http://example.com/repo"),
            "git_branch": "main",
            "git_tag": "v1.0",
            "git_commit_hash": "abc123",
            "created_by": "user1",
            "created_at": datetime(2023, 1, 1, 0, 0, 0),
            "last_updated_by": "user2",
            "extra": {"key": "value"},
            "artifacts": [
                {
                    "kind": "output",
                    "uri": AnyUrl("http://example.com/artifact1"),
                    "label": "artifact1",
                    "id": uuid4(),
                    "created_at": datetime(2023, 1, 1, 0, 0, 0),
                    "updated_at": datetime(2023, 1, 2, 0, 0, 0),
                }
            ],
            "links": [
                {
                    "kind": "diagnostic",
                    "url": HttpUrl("http://example.com/link1"),
                    "label": "link1",
                    "id": uuid4(),
                    "created_at": datetime(2023, 1, 1, 0, 0, 0),
                    "updated_at": datetime(2023, 1, 2, 0, 0, 0),
                }
            ],
        }

        fields = {**required_fields, **optional_fields}

        simulation_out = SimulationOut(**fields)  # type: ignore

        for key, value in fields.items():
            if key in ["artifacts", "links"]:
                assert len(getattr(simulation_out, key)) == len(value)  # type: ignore
                for i, item in enumerate(value):  # type: ignore
                    for attr, attr_value in item.items():
                        assert (
                            getattr(getattr(simulation_out, key)[i], attr) == attr_value
                        )
            else:
                assert getattr(simulation_out, key) == value

    def test_grouped_artifacts_computed_field(self):
        simulation_out = SimulationOut(
            id=uuid4(),
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="new",
            machine_id=uuid4(),
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
            machine=MachineOut(
                id=uuid4(),
                name="Machine A",
                site="Data Center 1",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=True,
                notes="High-performance computing machine",
                created_at=datetime(2023, 1, 1, 0, 0, 0),
                updated_at=datetime(2023, 1, 2, 0, 0, 0),
            ),
            artifacts=[
                ArtifactOut(
                    kind=ArtifactKind.OUTPUT,
                    uri=AnyUrl("http://example.com/artifact1"),
                    label="artifact1",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
                ArtifactOut(
                    kind=ArtifactKind.ARCHIVE,
                    uri=AnyUrl("http://example.com/artifact2"),
                    label="artifact2",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
                ArtifactOut(
                    kind=ArtifactKind.OUTPUT,
                    uri=AnyUrl("http://example.com/artifact3"),
                    label="artifact3",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
            ],
        )  # type: ignore

        grouped = simulation_out.grouped_artifacts
        assert len(grouped()) == 2, "There should be 2 groups of artifacts."
        assert len(grouped()["output"]) == 2, "There should be 2 output artifacts."
        assert len(grouped()["archive"]) == 1, "There should be 1 archive artifact."

    def test_grouped_links_computed_field(self):
        simulation_out = SimulationOut(
            id=uuid4(),
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="new",
            machine_id=uuid4(),
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
            machine=MachineOut(
                id=uuid4(),
                name="Machine A",
                site="Data Center 1",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=True,
                notes="High-performance computing machine",
                created_at=datetime(2023, 1, 1, 0, 0, 0),
                updated_at=datetime(2023, 1, 2, 0, 0, 0),
            ),
            links=[
                ExternalLinkOut(
                    kind=ExternalLinkKind.DIAGNOSTIC,
                    url=HttpUrl("http://example.com/link1"),
                    label="link1",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
                ExternalLinkOut(
                    kind=ExternalLinkKind.PERFORMANCE,
                    url=HttpUrl("http://example.com/link2"),
                    label="link2",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
            ],
        )  # type: ignore

        grouped = simulation_out.grouped_links
        assert len(grouped()) == 2, "There should be 2 groups of links."
        assert len(grouped()["diagnostic"]) == 1, "There should be 2 diagnostic links."
        assert len(grouped()["performance"]) == 1, (
            "There should be 2 performance links."
        )
