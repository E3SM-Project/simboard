from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import HttpUrl, ValidationError

from app.common.schemas.utils import to_snake_case
from app.features.machine.schemas import MachineOut
from app.features.simulation.schemas import (
    ArtifactCreate,
    ArtifactKind,
    ArtifactOut,
    CaseDetailOut,
    CaseSummaryOut,
    CaseUpdate,
    ExternalLinkKind,
    ExternalLinkOut,
    SimulationCreate,
    SimulationOut,
    SimulationSummaryCapabilitiesOut,
    SimulationSummaryOut,
    SimulationUpdate,
    _normalize_optional_label,
)
from app.features.user.schemas import UserPreview


class TestSimulationCreateSchema:
    def test_valid_simulation_create_required_fields(self):
        payload = {
            "caseId": uuid4(),
            "executionId": "1081156.251218-200923",
            "caseHash": "abc123",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "experimental",
            "status": "created",
            "simulationStartDate": datetime(2023, 1, 1, 0, 0, 0),
            "createdBy": uuid4(),
            "lastUpdatedBy": uuid4(),
        }

        simulation_create = SimulationCreate(**payload)
        for key, value in payload.items():
            snake_case_key = to_snake_case(key)
            assert getattr(simulation_create, snake_case_key) == value

    def test_valid_simulation_create_optional_fields(self):
        payload = {
            "caseId": uuid4(),
            "executionId": "1081156.251218-200923",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "experimental",
            "status": "created",
            "simulationStartDate": datetime(2023, 1, 1, 0, 0, 0),
            "gitTag": "v1.0",
            "gitCommitHash": "abc123",
            "campaign": "campaign1",
            "experimentType": "exp1",
            "simulationEndDate": datetime(2023, 12, 31, 0, 0, 0),
            "runStartDate": datetime(2023, 1, 1, 0, 0, 0),
            "runEndDate": datetime(2023, 12, 31, 0, 0, 0),
            "compiler": "gcc",
            "notesMarkdown": "Some notes",
            "knownIssues": "No known issues",
            "gitBranch": "main",
            "gitRepositoryUrl": HttpUrl("http://example.com/repo"),
            "createdBy": uuid4(),
            "lastUpdatedBy": uuid4(),
            "extra": {"key": "value"},
            "artifacts": [
                {
                    "kind": "output",
                    "uri": "http://example.com/artifact1",
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

        simulation_create = SimulationCreate(**payload)
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


class TestSimulationUpdateSchema:
    def test_normalize_optional_label_accepts_none(self):
        assert _normalize_optional_label(None) is None

    def test_accepts_allowed_optional_fields(self):
        payload = {
            "simulationType": "production",
            "status": "completed",
            "description": "Updated description",
            "campaign": "campaign-1",
            "experimentType": "historical",
            "keyFeatures": "feature a\nfeature b",
            "knownIssues": "issue a",
            "notesMarkdown": "## Notes",
        }

        update = SimulationUpdate(**payload)

        for key, value in payload.items():
            assert getattr(update, to_snake_case(key)) == value

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("compiler", "intel"),
            ("gitRepositoryUrl", "https://example.com/repo"),
            ("gitBranch", "main"),
            ("gitTag", "v1.2.3"),
            ("gitCommitHash", "abc123"),
        ],
    )
    def test_rejects_non_editable_fields(self, field_name: str, value: str):
        with pytest.raises(ValidationError):
            SimulationUpdate(**{field_name: value})

    def test_rejects_invalid_predefined_value(self):
        with pytest.raises(ValidationError):
            SimulationUpdate(status="done")

    @pytest.mark.parametrize("field_name", ["status", "simulationType"])
    def test_rejects_explicit_null_for_non_nullable_enums(self, field_name: str):
        with pytest.raises(ValidationError):
            SimulationUpdate(**{field_name: None})

    @pytest.mark.parametrize("field_name", ["artifacts", "links"])
    def test_rejects_explicit_null_for_resource_fields(self, field_name: str):
        with pytest.raises(ValidationError):
            SimulationUpdate(**{field_name: None})

    def test_rejects_out_of_scope_field(self):
        with pytest.raises(ValidationError):
            SimulationUpdate(caseName="new-case")

    def test_accepts_resource_replacement_payloads(self):
        update = SimulationUpdate(
            artifacts=[
                {
                    "kind": "archive",
                    "uri": "  /global/cfs/project/archive/run-1  ",
                    "label": "  Main archive  ",
                }
            ],
            links=[
                {
                    "kind": "docs",
                    "url": "https://example.com/docs/run-1",
                    "label": "  Run docs  ",
                }
            ],
        )

        assert update.artifacts is not None
        assert update.links is not None
        assert update.artifacts[0].uri == "/global/cfs/project/archive/run-1"
        assert update.artifacts[0].label == "Main archive"
        assert str(update.links[0].url) == "https://example.com/docs/run-1"
        assert update.links[0].label == "Run docs"

    def test_rejects_blank_artifact_uri(self):
        with pytest.raises(ValidationError):
            SimulationUpdate(
                artifacts=[{"kind": "output", "uri": "   ", "label": "Blank"}]
            )

    @pytest.mark.parametrize("uri", [None, 123])
    def test_artifact_create_rejects_non_string_uri(self, uri):
        with pytest.raises(ValidationError):
            ArtifactCreate(kind="output", uri=uri, label="Bad")

    @pytest.mark.parametrize("uri", [None, 123])
    def test_update_rejects_non_string_artifact_uri(self, uri):
        with pytest.raises(ValidationError):
            SimulationUpdate(artifacts=[{"kind": "output", "uri": uri, "label": "Bad"}])

    def test_rejects_invalid_external_link_url(self):
        with pytest.raises(ValidationError):
            SimulationUpdate(
                links=[{"kind": "diagnostic", "url": "not-a-url", "label": "Bad"}]
            )

    def test_rejects_duplicate_resource_pairs(self):
        with pytest.raises(ValidationError):
            SimulationUpdate(
                artifacts=[
                    {"kind": "archive", "uri": "/tmp/archive", "label": "One"},
                    {"kind": "archive", "uri": "/tmp/archive", "label": "Two"},
                ]
            )

        with pytest.raises(ValidationError):
            SimulationUpdate(
                links=[
                    {
                        "kind": "docs",
                        "url": "https://example.com/docs",
                        "label": "One",
                    },
                    {
                        "kind": "docs",
                        "url": "https://example.com/docs",
                        "label": "Two",
                    },
                ]
            )

    def test_update_resource_validators_accept_none_when_called_directly(self):
        assert SimulationUpdate.validate_update_artifacts(None) is None
        assert SimulationUpdate.validate_update_links(None) is None


class TestCaseUpdateSchema:
    def test_omitted_fields_produce_empty_patch(self):
        update = CaseUpdate()

        assert update.model_dump(exclude_unset=True) == {}
        assert update.model_fields_set == set()

    def test_explicit_null_is_preserved_for_clear(self):
        update = CaseUpdate(description=None)

        assert update.model_dump(exclude_unset=True) == {"description": None}
        assert "description" in update.model_fields_set

    @pytest.mark.parametrize(
        ("input_field", "model_field"),
        [
            ("description", "description"),
            ("keyFeatures", "key_features"),
            ("knownIssues", "known_issues"),
            ("notesMarkdown", "notes_markdown"),
        ],
    )
    def test_blank_strings_normalize_to_null(self, input_field: str, model_field: str):
        update = CaseUpdate(**{input_field: "   "})

        assert getattr(update, model_field) is None
        assert update.model_dump(exclude_unset=True) == {model_field: None}

    def test_rejects_out_of_scope_fields(self):
        with pytest.raises(ValidationError):
            CaseUpdate(caseName="new-case")


class TestSimulationOutSchema:
    def test_valid_simulation_out_required_fields(self):
        # Arrange: Define the required fields
        case_id = uuid4()
        fields = {
            "id": uuid4(),
            "case_id": case_id,
            "case_name": "test_case",
            "execution_id": "1081156.251218-200923",
            "case_hash": "abc123",
            "compset": "AQUAPLANET",
            "compset_alias": "QPC4",
            "grid_name": "f19_f19",
            "grid_resolution": "1.9x2.5",
            "initialization_type": "startup",
            "simulation_type": "experimental",
            "status": "created",
            "machine_id": uuid4(),
            "simulation_start_date": datetime(2023, 1, 1, 0, 0, 0),
            "created_by": uuid4(),
            "created_by_user": UserPreview(
                id=uuid4(), email="creator@example.com", role="user"
            ),
            "created_at": datetime(2023, 1, 1, 0, 0, 0),
            "updated_at": datetime(2023, 1, 2, 0, 0, 0),
            "last_updated_by_user": UserPreview(
                id=uuid4(), email="updater@example.com", role="user"
            ),
            "last_updated_by": uuid4(),
            "summary_capabilities": SimulationSummaryCapabilitiesOut(
                llm_available=False,
                auto_generate_deterministic_on_load=True,
            ),
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
        simulation_out = SimulationOut(**fields)

        # Assert: Validate all fields
        for key, value in fields.items():
            assert getattr(simulation_out, key) == value, (
                f"Field '{key}' does not match the expected value."
            )

        # Assert: Validate optional fields are set to their defaults
        optional_fields = [
            "campaign",
            "experiment_type",
            "case_group",
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

    def test_valid_simulation_out_optional_fields(self):
        case_id = uuid4()
        required_fields = {
            "id": uuid4(),
            "case_id": case_id,
            "case_name": "test_case",
            "execution_id": "1081156.251218-200923",
            "case_hash": "abc123",
            "compset": "AQUAPLANET",
            "compset_alias": "QPC4",
            "grid_name": "f19_f19",
            "grid_resolution": "1.9x2.5",
            "initialization_type": "startup",
            "simulation_type": "experimental",
            "status": "created",
            "machine_id": uuid4(),
            "simulation_start_date": datetime(2023, 1, 1, 0, 0, 0),
            "created_by": uuid4(),
            "created_by_user": UserPreview(
                id=uuid4(), email="creator@example.com", role="user"
            ),
            "created_at": datetime(2023, 1, 1, 0, 0, 0),
            "updated_at": datetime(2023, 1, 2, 0, 0, 0),
            "last_updated_by_user": UserPreview(
                id=uuid4(), email="updater@example.com", role="user"
            ),
            "last_updated_by": uuid4(),
            "summary_capabilities": SimulationSummaryCapabilitiesOut(
                llm_available=False,
                auto_generate_deterministic_on_load=True,
            ),
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
            "campaign": "campaign1",
            "experiment_type": "exp1",
            "case_group": "group1",
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
            "extra": {"key": "value"},
            "artifacts": [
                {
                    "kind": "output",
                    "uri": "http://example.com/artifact1",
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

        simulation_out = SimulationOut(**fields)

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
        simulation_out = SimulationOut(  # type: ignore[call-arg]
            id=uuid4(),
            case_id=uuid4(),
            case_name="test_case",
            execution_id="1081156.251218-200923",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=uuid4(),
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            created_by=uuid4(),
            created_by_user=UserPreview(
                id=uuid4(), email="creator@example.com", role="user"
            ),
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
            last_updated_by_user=UserPreview(
                id=uuid4(), email="updater@example.com", role="user"
            ),
            last_updated_by=uuid4(),
            summary_capabilities=SimulationSummaryCapabilitiesOut(
                llm_available=False,
                auto_generate_deterministic_on_load=True,
            ),
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
                    uri="http://example.com/artifact1",
                    label="artifact1",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
                ArtifactOut(
                    kind=ArtifactKind.ARCHIVE,
                    uri="http://example.com/artifact2",
                    label="artifact2",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
                ArtifactOut(
                    kind=ArtifactKind.OUTPUT,
                    uri="http://example.com/artifact3",
                    label="artifact3",
                    id=uuid4(),
                    created_at=datetime(2023, 1, 1, 0, 0, 0),
                    updated_at=datetime(2023, 1, 2, 0, 0, 0),
                ),
            ],
        )

        grouped = simulation_out.grouped_artifacts
        assert len(grouped) == 2, "There should be 2 groups of artifacts."  # type: ignore
        assert len(grouped["output"]) == 2, "There should be 2 output artifacts."  # type: ignore
        assert len(grouped["archive"]) == 1, "There should be 1 archive artifact."  # type: ignore

    def test_grouped_links_computed_field(self):
        simulation_out = SimulationOut(  # type: ignore[call-arg]
            id=uuid4(),
            case_id=uuid4(),
            case_name="test_case",
            execution_id="1081156.251218-200923",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="experimental",
            status="created",
            machine_id=uuid4(),
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            created_by=uuid4(),
            created_by_user=UserPreview(
                id=uuid4(), email="creator@example.com", role="user"
            ),
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
            last_updated_by_user=UserPreview(
                id=uuid4(), email="updater@example.com", role="user"
            ),
            last_updated_by=uuid4(),
            summary_capabilities=SimulationSummaryCapabilitiesOut(
                llm_available=False,
                auto_generate_deterministic_on_load=True,
            ),
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
        )

        grouped = simulation_out.grouped_links
        assert len(grouped) == 2, "There should be 2 groups of links."  # type: ignore
        assert len(grouped["diagnostic"]) == 1, "There should be 2 diagnostic links."  # type: ignore
        assert len(grouped["performance"]) == 1, "There should be 2 performance links."  # type: ignore


class TestSimulationSummaryOutSchema:
    def test_case_hash_schema_descriptions_reflect_grouping_semantics(self):
        create_schema = SimulationCreate.model_json_schema()
        create_description = create_schema["properties"]["caseHash"]["description"]
        assert (
            "group related executions or sub-cases within a case" in create_description
        )
        assert "not top-level case identity" in create_description

        summary_schema = SimulationSummaryOut.model_json_schema()
        summary_description = summary_schema["properties"]["caseHash"]["description"]
        assert (
            "group related executions or sub-cases within a case" in summary_description
        )

        simulation_out_schema = SimulationOut.model_json_schema()
        out_description = simulation_out_schema["properties"]["caseHash"]["description"]
        assert "group related executions or sub-cases within a case" in out_description
        assert "not top-level case identity" in out_description

    def test_valid_summary_fields(self):
        summary = SimulationSummaryOut(
            id=uuid4(),
            execution_id="1081156.251218-200923",
            case_hash=None,
            status="created",
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            simulation_end_date=None,
        )
        assert summary.case_hash is None
        assert summary.simulation_end_date is None

    def test_non_reference_with_changes(self):
        summary = SimulationSummaryOut(
            id=uuid4(),
            execution_id="1081290.251218-211543",
            case_hash="hash-2",
            status="completed",
            simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
            simulation_end_date=datetime(2023, 12, 31, 0, 0, 0),
        )
        assert summary.case_hash == "hash-2"
        assert summary.simulation_end_date == datetime(2023, 12, 31, 0, 0, 0)


class TestCaseSchemas:
    def test_case_summary_out_with_nested_simulations(self):
        sim_id = uuid4()
        case_out = CaseSummaryOut(
            id=uuid4(),
            name="v3.LR.historical_0121",
            case_group="ensemble_v3",
            simulations=[
                SimulationSummaryOut(
                    id=sim_id,
                    execution_id="1081156.251218-200923",
                    case_hash="hash-1",
                    status="completed",
                    simulation_start_date=datetime(2023, 1, 1, 0, 0, 0),
                    simulation_end_date=datetime(2023, 12, 31, 0, 0, 0),
                ),
                SimulationSummaryOut(
                    id=uuid4(),
                    execution_id="1081290.251218-211543",
                    case_hash="hash-2",
                    status="completed",
                    simulation_start_date=datetime(2023, 2, 1, 0, 0, 0),
                    simulation_end_date=None,
                ),
            ],
            machine_names=["chrysalis"],
            hpc_usernames=["ac.tvo"],
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
        )
        assert case_out.name == "v3.LR.historical_0121"
        assert case_out.case_group == "ensemble_v3"
        assert len(case_out.simulations) == 2
        assert case_out.simulations[0].case_hash == "hash-1"
        assert case_out.machine_names == ["chrysalis"]
        assert case_out.hpc_usernames == ["ac.tvo"]
        assert case_out.simulations[1].case_hash == "hash-2"

    def test_case_detail_out_includes_shared_metadata(self):
        case_out = CaseDetailOut(
            id=uuid4(),
            name="empty_case",
            case_group=None,
            description="Shared description",
            key_features="Shared features",
            known_issues="Shared known issues",
            notes_markdown="## Notes",
            simulations=[],
            machine_names=[],
            hpc_usernames=[],
            created_at=datetime(2023, 1, 1, 0, 0, 0),
            updated_at=datetime(2023, 1, 2, 0, 0, 0),
        )
        assert case_out.description == "Shared description"
        assert case_out.key_features == "Shared features"
        assert case_out.known_issues == "Shared known issues"
        assert case_out.notes_markdown == "## Notes"
