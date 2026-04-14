from datetime import datetime
from pathlib import Path
from typing import Mapping
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from dateutil import parser as real_dateutil_parser
from sqlalchemy.orm import Session

from app.features.ingestion.ingest import (
    SimulationCreateDraft,
    _build_config_snapshot,
    _build_simulation_create_draft,
    _get_or_create_case,
    _get_reference_metadata_for_case,
    _normalize_git_url,
    _normalize_simulation_status,
    _normalize_simulation_type,
    _stringify_config_value,
    _validate_simulation_create,
    ingest_archive,
)
from app.features.ingestion.models import (
    Ingestion,
    IngestionSourceType,
    IngestionStatus,
)
from app.features.ingestion.parsers.types import ParsedSimulation
from app.features.machine.models import Machine
from app.features.simulation.config_delta import SimulationConfigSnapshot
from app.features.simulation.enums import ArtifactKind, SimulationStatus, SimulationType
from app.features.simulation.models import Case, Simulation
from app.features.simulation.schemas import SimulationCreate
from app.features.user.models import User


def _parsed_simulations_from_mapping(
    simulations_by_dir: Mapping[str, Mapping[str, str | None]],
) -> list[ParsedSimulation]:
    parsed_simulations: list[ParsedSimulation] = []

    for execution_dir, metadata in simulations_by_dir.items():
        parsed_simulations.append(
            ParsedSimulation(
                execution_dir=execution_dir,
                execution_id=_require_execution_id(metadata, execution_dir),
                case_name=metadata.get("case_name"),
                case_group=metadata.get("case_group"),
                machine=metadata.get("machine"),
                hpc_username=metadata.get("hpc_username") or metadata.get("user"),
                compset=metadata.get("compset"),
                compset_alias=metadata.get("compset_alias"),
                grid_name=metadata.get("grid_name"),
                grid_resolution=metadata.get("grid_resolution"),
                campaign=metadata.get("campaign"),
                experiment_type=metadata.get("experiment_type"),
                initialization_type=metadata.get("initialization_type"),
                simulation_start_date=metadata.get("simulation_start_date"),
                simulation_end_date=metadata.get("simulation_end_date"),
                run_start_date=metadata.get("run_start_date"),
                run_end_date=metadata.get("run_end_date"),
                compiler=metadata.get("compiler"),
                git_repository_url=metadata.get("git_repository_url"),
                git_branch=metadata.get("git_branch"),
                git_tag=metadata.get("git_tag"),
                git_commit_hash=metadata.get("git_commit_hash"),
                status=metadata.get("status"),
                output_path=metadata.get("output_path"),
                archive_path=metadata.get("archive_path"),
                case_root=metadata.get("case_root"),
                postprocessing_script=metadata.get("postprocessing_script"),
            )
        )

    return parsed_simulations


def _require_execution_id(
    metadata: Mapping[str, str | None], execution_dir: str
) -> str:
    execution_id = metadata.get("execution_id")
    if not execution_id:
        raise AssertionError(
            f"Mocked ParsedSimulation for '{execution_dir}' must define execution_id"
        )

    return execution_id


class TestIngestArchive:
    """Tests for the ingest_archive public API.

    Tests cover all aspects of simulation ingestion including:
    - Datetime parsing with various formats and timezone awareness
    - Machine lookup and validation
    - Simulation key extraction for deduplication
    - Metadata schema mapping validation
    - Archive parsing integration
    - Error handling and propagation
    """

    def test_stringify_config_value_falls_back_to_str_for_non_string_objects(self):
        class ValueObject:
            def __str__(self) -> str:
                return "42"

        assert _stringify_config_value(ValueObject()) == "42"

    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        """Create a test machine in the database."""
        machine = Machine(
            name=name,
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return machine

    def test_returns_list_of_simulation_create(self, db: Session) -> None:
        """Test that ingest_archive returns list of SimulationCreate objects."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations: dict[str, dict[str, str | None]] = {
            "/path/to/1081156.251218-200923": {
                "execution_id": "1081156.251218-200923",
                "case_name": "case1",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid1",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert isinstance(ingest_result.simulations, list)
        assert len(ingest_result.simulations) == 1
        assert isinstance(ingest_result.simulations[0], SimulationCreate)
        assert ingest_result.simulations[0].execution_id == "1081156.251218-200923"
        # Verify Case was created
        case = db.query(Case).filter(Case.name == "case1").first()
        assert case is not None
        assert ingest_result.simulations[0].case_id == case.id

    def test_handles_multiple_simulations(self, db: Session) -> None:
        """Test ingesting archive with multiple simulations."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations: dict[str, dict[str, str | None]] = {
            "/path/to/1081157.251218-200924": {
                "execution_id": "1081157.251218-200924",
                "case_name": "case1",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid1",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            },
            "/path/to/1081158.251218-200925": {
                "execution_id": "1081158.251218-200925",
                "case_name": "case2",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid2",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            },
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert len(ingest_result.simulations) == 2
        exec_ids = {s.execution_id for s in ingest_result.simulations}
        assert exec_ids == {"1081157.251218-200924", "1081158.251218-200925"}

    def test_returns_empty_list_for_empty_archive(self, db: Session) -> None:
        """Test that empty archive returns empty list."""
        with patch("app.features.ingestion.ingest.main_parser", return_value=([], 0)):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert isinstance(ingest_result.simulations, list)
        assert len(ingest_result.simulations) == 0

    def test_accepts_string_paths(self, db: Session) -> None:
        """Test that archive_path and output_dir accept strings."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081159.251218-200926": {
                "execution_id": "1081159.251218-200926",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ) as mock_main_parser:
            ingest_result = ingest_archive("/tmp/archive.zip", "/tmp/out", db)

        # Verify main_parser was called with Path objects
        assert ingest_result.simulations is not None
        mock_main_parser.assert_called_once()
        args = mock_main_parser.call_args[0]
        assert isinstance(args[0], Path)
        assert isinstance(args[1], Path)

    def test_propagates_mapping_errors(self, db: Session) -> None:
        """Test that mapping errors are collected and ingestion continues."""
        mock_simulations = {
            "/path/to/1081160.251218-200927": {
                "execution_id": "1081160.251218-200927",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": "nonexistent-machine",
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert ingest_result.simulations == []
        assert len(ingest_result.errors) == 1
        assert ingest_result.errors[0]["error_type"] == "LookupError"
        assert "nonexistent-machine" in ingest_result.errors[0]["error"]

    def test_parses_various_datetime_formats_through_public_api(
        self, db: Session
    ) -> None:
        """Test datetime parsing with various formats through public API.

        This test verifies the _parse_datetime_field behavior by using it
        through the public ingest_archive API.
        """
        machine = self._create_machine(db, "test-machine")

        test_cases = [
            "2020-01-01",
            "2020-01-01 12:30:45",
            "2020-01-01T12:30:45",
            "01/01/2020",
            "Jan 1, 2020",
        ]

        for idx, date_str in enumerate(test_cases):
            mock_simulations = {
                f"/path/to/108200{idx}.251218-200900": {
                    "execution_id": f"108200{idx}.251218-200900",
                    "case_name": f"case1_{date_str}",
                    "compset": "test",
                    "compset_alias": "test_alias",
                    "grid_name": "grid",
                    "grid_resolution": "0.9x1.25",
                    "machine": machine.name,
                    "simulation_start_date": date_str,
                    "initialization_type": "test",
                    "simulation_type": "test_type",
                    "status": None,
                    "experiment_type": None,
                    "campaign": None,
                    "run_start_date": None,
                    "run_end_date": None,
                    "compiler": None,
                    "git_repository_url": None,
                    "git_branch": None,
                    "git_tag": None,
                    "git_commit_hash": None,
                    "created_by": None,
                    "last_updated_by": None,
                }
            }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert len(ingest_result.simulations) == 1
        assert isinstance(ingest_result.simulations[0].simulation_start_date, datetime)
        assert ingest_result.simulations[0].simulation_start_date.tzinfo is not None

    def test_missing_required_fields_raise_validation_error(self, db: Session) -> None:
        """Test that missing required fields are captured as errors."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081170.251218-200930": {
                "execution_id": "1081170.251218-200930",
                "case_name": None,
                "compset": None,
                "compset_alias": "test_alias",
                "grid_name": None,
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": None,
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert ingest_result.simulations == []
        assert len(ingest_result.errors) == 1
        assert ingest_result.errors[0]["error_type"] == "ValueError"

    def test_machine_lookup_and_validation_through_public_api(
        self, db: Session
    ) -> None:
        """Test machine lookup and validation through public API.

        This test verifies that the public API correctly looks up machines
        and propagates errors for missing machines (testing _resolve_machine_id
        and machine lookup behavior).
        """
        machine = self._create_machine(db, "valid-machine")

        # Create valid simulation
        valid_mock = {
            "/path/to/1081171.251218-200931": {
                "execution_id": "1081171.251218-200931",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(valid_mock), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert len(ingest_result.simulations) == 1
        assert ingest_result.simulations[0].machine_id == machine.id

        # Test with missing machine
        invalid_mock = {
            "/path/to/1081172.251218-200932": {
                "execution_id": "1081172.251218-200932",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": "nonexistent",
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(invalid_mock), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert ingest_result.simulations == []
        assert len(ingest_result.errors) == 1
        assert ingest_result.errors[0]["error_type"] == "LookupError"
        assert "Machine 'nonexistent'" in ingest_result.errors[0]["error"]

    @pytest.mark.parametrize("machine_alias", ["pm", "pm-cpu", "pm-gpu"])
    def test_machine_aliases_resolve_to_perlmutter(
        self, db: Session, machine_alias: str
    ) -> None:
        machine = db.query(Machine).filter(Machine.name == "perlmutter").first()
        if machine is None:
            machine = self._create_machine(db, "perlmutter")

        mock_simulations = {
            "/path/to/1081175.251218-200935": {
                "execution_id": "1081175.251218-200935",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine_alias,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert len(ingest_result.simulations) == 1
        assert ingest_result.simulations[0].machine_id == machine.id


class TestIngestArchiveContinued(TestIngestArchive):
    def test_normalize_simulation_type_handles_none_and_blank(self) -> None:
        assert _normalize_simulation_type(None) == SimulationType.UNKNOWN
        assert _normalize_simulation_type("   ") == SimulationType.UNKNOWN

    def test_normalize_simulation_type_handles_valid_and_unknown_values(self) -> None:
        assert _normalize_simulation_type("production") == SimulationType.PRODUCTION
        assert _normalize_simulation_type("TEST") == SimulationType.TEST
        assert _normalize_simulation_type("not-a-type") == SimulationType.UNKNOWN

    def test_normalize_simulation_status_handles_none_and_blank(self) -> None:
        assert _normalize_simulation_status(None) == SimulationStatus.CREATED
        assert _normalize_simulation_status("   ") == SimulationStatus.CREATED

    def test_normalize_simulation_status_handles_valid_and_unknown_values(self) -> None:
        assert _normalize_simulation_status("running") == SimulationStatus.RUNNING
        assert _normalize_simulation_status("COMPLETED") == SimulationStatus.COMPLETED
        assert _normalize_simulation_status("not-a-status") == SimulationStatus.CREATED

    def test_timezone_aware_datetime_parsing_through_public_api(
        self, db: Session
    ) -> None:
        """Test timezone-aware datetime parsing through public API.

        This test verifies that all parsed datetimes are timezone-aware.
        """
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081173.251218-200933": {
                "execution_id": "1081173.251218-200933",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": "2020-01-01",
                "run_end_date": "2020-12-31",
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert len(ingest_result.simulations) == 1
            # All datetime fields should be timezone-aware
            assert ingest_result.simulations[0].simulation_start_date.tzinfo is not None
            if ingest_result.simulations[0].run_start_date:
                assert ingest_result.simulations[0].run_start_date.tzinfo is not None
            if ingest_result.simulations[0].run_end_date:
                assert ingest_result.simulations[0].run_end_date.tzinfo is not None

    def test_handles_optional_fields_through_public_api(self, db: Session) -> None:
        """Test optional field handling through public API.

        This test verifies that optional fields are properly mapped when
        provided in the metadata.
        """
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081174.251218-200934": {
                "execution_id": "1081174.251218-200934",
                "case_name": "case1",
                "compset": "FHIST",
                "compset_alias": "FHIST_f09_fe",
                "grid_name": "f09_fe",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "BRANCH",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": "historical",
                "campaign": "CMIP6",
                "case_group": "test_group",
                "run_start_date": "2020-01-01 00:00:00",
                "run_end_date": "2020-12-31 23:59:59",
                "compiler": "gcc",
                "git_repository_url": "https://github.com/test/repo",
                "git_branch": "main",
                "git_tag": "v1.0.0",
                "git_commit_hash": "abc123",
                "created_by": "user1",
                "last_updated_by": "user2",
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert len(ingest_result.simulations) == 1
            assert ingest_result.simulations[0].experiment_type == "historical"
            assert ingest_result.simulations[0].campaign == "CMIP6"
            assert ingest_result.simulations[0].compiler == "gcc"
            assert (
                str(ingest_result.simulations[0].git_repository_url)
                == "https://github.com/test/repo"
            )
            assert ingest_result.simulations[0].git_branch == "main"
            assert ingest_result.simulations[0].git_tag == "v1.0.0"
            assert ingest_result.simulations[0].git_commit_hash == "abc123"

            # Verify case_group is stored on the Case, not the Simulation
            case = db.query(Case).filter(Case.name == "case1").first()
            assert case is not None
            assert case.case_group == "test_group"

    def test_skips_duplicate_simulations(self, db: Session) -> None:
        """Test that duplicate simulations are skipped during ingestion.

        This test verifies the deduplication logic by:
        1. Creating a simulation directly in the database with an execution_id
        2. Attempting to ingest a simulation with the same execution_id
        3. Verifying it's skipped and not returned
        """
        machine = self._create_machine(db, "test-machine")

        # Create a test user for created_by and last_updated_by fields
        user = User(
            id=uuid4(), email="test@example.com", is_active=True, is_superuser=False
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="test_skips_duplicate_simulations",
            machine_id=machine.id,
            triggered_by=user.id,
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        # Create a Case and Simulation directly in the database
        case = Case(name="existing_case")
        db.add(case)
        db.flush()

        existing_sim = Simulation(
            case_id=case.id,
            execution_id="1081175.251218-200935",
            compset="FHIST",
            compset_alias="FHIST_f09_fe",
            grid_name="grid",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            simulation_type="test",
            status=SimulationStatus.CREATED,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
        )
        db.add(existing_sim)
        db.commit()

        # Try to ingest a simulation with the same execution_id
        mock_simulations = {
            "/path/to/1081175.251218-200935": {
                "execution_id": "1081175.251218-200935",
                "case_name": "existing_case",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Duplicate should be skipped, result should be empty
            assert len(ingest_result.simulations) == 0

    def test_validation_error_does_not_persist_empty_case(self, db: Session) -> None:
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081175.251218-200940": {
                "execution_id": "1081175.251218-200940",
                "case_name": "orphan_case_validation",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": None,
                "initialization_type": "test",
                "simulation_type": "test",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert ingest_result.simulations == []
        assert len(ingest_result.errors) == 1
        assert ingest_result.errors[0]["error_type"] == "ValidationError"
        assert (
            db.query(Case).filter(Case.name == "orphan_case_validation").first() is None
        )

    def test_duplicate_does_not_persist_new_empty_case(self, db: Session) -> None:
        machine = self._create_machine(db, "test-machine")

        user = User(
            id=uuid4(), email="test@example.com", is_active=True, is_superuser=False
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="test_duplicate_does_not_persist_new_empty_case",
            machine_id=machine.id,
            triggered_by=user.id,
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        case = Case(name="existing_case")
        db.add(case)
        db.flush()

        existing_sim = Simulation(
            case_id=case.id,
            execution_id="1081175.251218-200941",
            compset="FHIST",
            compset_alias="FHIST_f09_fe",
            grid_name="grid",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            simulation_type="test",
            status=SimulationStatus.CREATED,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
        )
        db.add(existing_sim)
        db.commit()

        mock_simulations = {
            "/path/to/1081175.251218-200941": {
                "execution_id": "1081175.251218-200941",
                "case_name": "orphan_case_duplicate",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert ingest_result.created_count == 0
        assert ingest_result.duplicate_count == 1
        assert ingest_result.simulations == []
        assert (
            db.query(Case).filter(Case.name == "orphan_case_duplicate").first() is None
        )

    def test_ingest_archive_counts(self, db: Session) -> None:
        """Test that summary counts reflect created and duplicate simulations."""
        machine = self._create_machine(db, "test-machine")

        user = User(
            id=uuid4(), email="test@example.com", is_active=True, is_superuser=False
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="test_ingest_archive_counts",
            machine_id=machine.id,
            triggered_by=user.id,
            status=IngestionStatus.SUCCESS,
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )
        db.add(ingestion)
        db.flush()

        case = Case(name="existing_case")
        db.add(case)
        db.flush()

        existing_sim = Simulation(
            case_id=case.id,
            execution_id="1081176.251218-200936",
            compset="FHIST",
            compset_alias="FHIST_f09_fe",
            grid_name="grid",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            simulation_type="test",
            status=SimulationStatus.CREATED,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
        )
        db.add(existing_sim)
        db.commit()

        mock_simulations = {
            "/path/to/1081176.251218-200936": {
                "execution_id": "1081176.251218-200936",
                "case_name": "existing_case",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            },
            "/path/to/1081177.251218-200937": {
                "execution_id": "1081177.251218-200937",
                "case_name": "new_case",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2021-01-01",
                "initialization_type": "test",
                "simulation_type": "test",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            },
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert ingest_result.created_count == 1
            assert ingest_result.duplicate_count == 1
            assert len(ingest_result.simulations) == 1
            assert ingest_result.simulations[0].execution_id == "1081177.251218-200937"

    def test_ingest_archive_empty_archive(self, db: Session) -> None:
        """Test summary counts when the archive contains no simulations."""
        with patch("app.features.ingestion.ingest.main_parser", return_value=([], 0)):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert ingest_result.simulations == []
            assert ingest_result.created_count == 0
            assert ingest_result.duplicate_count == 0

    def test_handles_invalid_datetime_gracefully(self, db: Session) -> None:
        """Test that invalid datetimes are handled without raising.

        This test verifies the exception handling in _parse_datetime_field
        by testing with various invalid date formats that trigger the except block.
        """
        machine = self._create_machine(db, "test-machine")

        # Create a simulation with an invalid run_start_date
        # This will be parsed but not raise an error
        mock_simulations = {
            "/path/to/1081178.251218-200938": {
                "execution_id": "1081178.251218-200938",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,  # None should parse gracefully
                "run_end_date": None,  # None should parse gracefully
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Should succeed with optional dates as None
            assert len(ingest_result.simulations) == 1
            assert ingest_result.simulations[0].run_start_date is None
            assert ingest_result.simulations[0].run_end_date is None

    def test_parse_datetime_field_exception_handling(self, db: Session) -> None:
        """Test exception handling in _parse_datetime_field.

        This test ensures that exceptions raised during datetime parsing are logged
        and None is returned instead of propagating the error.
        """
        machine = self._create_machine(db, "test-machine")

        # Mock dateutil_parser.parse to raise an exception for specific inputs
        # This ensures we exercise the except block in _parse_datetime_field
        mock_simulations = {
            "/path/to/1081179.251218-200939": {
                "execution_id": "1081179.251218-200939",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": "INVALID_DATE_STRING_FOR_TESTING",
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        original_parse = real_dateutil_parser.parse

        def mock_parse_wrapper(date_str, *args, **kwargs):
            """Mock parser that raises ValueError for specific inputs."""
            if date_str == "INVALID_DATE_STRING_FOR_TESTING":
                raise ValueError("Forced test error for coverage")
            return original_parse(date_str, *args, **kwargs)

        with (
            patch(
                "app.features.ingestion.ingest.main_parser",
                return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
            ),
            patch(
                "app.features.ingestion.ingest.dateutil_parser.parse",
                side_effect=mock_parse_wrapper,
            ),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Should succeed with run_start_date as None (exception caught and logged)
            assert len(ingest_result.simulations) == 1
            assert ingest_result.simulations[0].run_start_date is None

    def test_missing_machine_name_in_metadata(self, db: Session) -> None:
        """Test error handling when machine name is missing from metadata."""
        mock_simulations = {
            "/path/to/1081180.251218-200940": {
                "execution_id": "1081180.251218-200940",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": None,  # Missing machine
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert ingest_result.simulations == []
            assert len(ingest_result.errors) == 1
            assert ingest_result.errors[0]["error_type"] == "ValueError"
            assert "Machine name is required" in ingest_result.errors[0]["error"]

    def test_missing_simulation_start_date(self, db: Session) -> None:
        """Test error when simulation_start_date cannot be parsed."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081181.251218-200941": {
                "execution_id": "1081181.251218-200941",
                "case_name": "case1",
                "compset": "test",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": None,  # Missing or invalid
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": None,
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert ingest_result.simulations == []
            assert len(ingest_result.errors) == 1
            assert ingest_result.errors[0]["error_type"] == "ValidationError"


class TestNormalizeGitUrl:
    """Tests for the _normalize_git_url helper function.

    Tests cover SSH to HTTPS URL conversion and various edge cases.
    """

    def test_converts_ssh_github_url_to_https(self) -> None:
        """Test conversion of SSH GitHub URL to HTTPS."""
        ssh_url = "git@github.com:E3SM-Project/E3SM.git"
        expected = "https://github.com/E3SM-Project/E3SM.git"
        assert _normalize_git_url(ssh_url) == expected

    def test_converts_ssh_gitlab_url_to_https(self) -> None:
        """Test conversion of SSH GitLab URL to HTTPS."""
        ssh_url = "git@gitlab.com:owner/repo.git"
        expected = "https://gitlab.com/owner/repo.git"
        assert _normalize_git_url(ssh_url) == expected

    def test_converts_ssh_url_with_nested_path(self) -> None:
        """Test conversion of SSH URL with nested repository path."""
        ssh_url = "git@github.com:organization/group/nested/repo.git"
        expected = "https://github.com/organization/group/nested/repo.git"
        assert _normalize_git_url(ssh_url) == expected

    def test_preserves_https_url(self) -> None:
        """Test that HTTPS URLs are preserved as-is."""
        https_url = "https://github.com/E3SM-Project/E3SM.git"
        assert _normalize_git_url(https_url) == https_url

    def test_preserves_http_url(self) -> None:
        """Test that HTTP URLs are preserved as-is."""
        http_url = "http://github.com/E3SM-Project/E3SM.git"
        assert _normalize_git_url(http_url) == http_url

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        assert _normalize_git_url(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        """Test that empty string returns None."""
        assert _normalize_git_url("") is None

    def test_handles_ssh_url_without_git_extension(self) -> None:
        """Test SSH URL conversion without .git extension."""
        ssh_url = "git@github.com:owner/repo"
        expected = "https://github.com/owner/repo"
        assert _normalize_git_url(ssh_url) == expected

    def test_handles_malformed_ssh_url_gracefully(self) -> None:
        """Test that malformed SSH URLs are returned as-is."""
        # Malformed SSH URL (no colon separator)
        malformed_url = "git@github.com"
        # Should return original since it can't be split on colon
        assert _normalize_git_url(malformed_url) == malformed_url

    def test_handles_other_git_formats(self) -> None:
        """Test that non-SSH non-HTTP URLs are returned as-is."""
        file_url = "file:///path/to/repo.git"
        assert _normalize_git_url(file_url) == file_url

    def test_ssh_url_conversion_integrated_in_ingest(self, db: Session) -> None:
        """Test SSH URL conversion through the full ingest pipeline.

        This test verifies that _normalize_git_url is actually used when
        processing metadata through ingest_archive.
        """
        machine = self._create_machine(db, "test-machine")

        # SSH URL in metadata
        mock_simulations = {
            "/path/to/1081182.251218-200942": {
                "execution_id": "1081182.251218-200942",
                "case_name": "case1",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": "test_type",
                "status": None,
                "experiment_type": None,
                "campaign": None,
                "run_start_date": None,
                "run_end_date": None,
                "compiler": None,
                "git_repository_url": "git@github.com:E3SM-Project/E3SM.git",
                "git_branch": None,
                "git_tag": None,
                "git_commit_hash": None,
                "created_by": None,
                "last_updated_by": None,
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Verify SSH URL was converted to HTTPS
            assert len(ingest_result.simulations) == 1
            assert str(ingest_result.simulations[0].git_repository_url) == (
                "https://github.com/E3SM-Project/E3SM.git"
            )

    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        """Create a test machine in the database."""
        machine = Machine(
            name=name,
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return machine


class TestReferenceRunIngestion:
    """Tests for reference run selection and config delta semantics.

    These tests verify that:
    - Multiple runs under the same casename are grouped properly
    - The first successful run is treated as reference
    - Subsequent runs record only config deltas
    - Idempotent re-ingestion works correctly
    - Incremental ingestion adds deltas without overwriting
    """

    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        """Create a test machine in the database."""
        machine = Machine(
            name=name,
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return machine

    @staticmethod
    def _make_metadata(
        execution_id: str,
        case_name: str = "case1",
        machine: str = "test-machine",
        simulation_start_date: str = "2020-01-01",
        **overrides: str | None,
    ) -> dict[str, str | None]:
        """Build a complete simulation metadata dict with sensible defaults."""
        base: dict[str, str | None] = {
            "execution_id": execution_id,
            "case_name": case_name,
            "compset": "FHIST",
            "compset_alias": "test_alias",
            "grid_name": "grid1",
            "grid_resolution": "0.9x1.25",
            "machine": machine,
            "simulation_start_date": simulation_start_date,
            "initialization_type": "test",
            "simulation_type": "test_type",
            "status": None,
            "experiment_type": None,
            "campaign": None,
            "run_start_date": None,
            "run_end_date": None,
            "compiler": None,
            "git_repository_url": None,
            "git_branch": None,
            "git_tag": None,
            "git_commit_hash": None,
            "created_by": None,
            "last_updated_by": None,
        }
        base.update(overrides)
        return base

    def test_reference_run_selected_from_multiple_runs(self, db: Session) -> None:
        """First run per case is reference (None deltas), subsequent runs
        with config differences get a delta dict."""
        self._create_machine(db, "test-machine")

        # Two runs with the same case_name but different compilers
        mock_simulations = {
            "/path/to/1081183.251218-200943": self._make_metadata(
                execution_id="1081183.251218-200943",
                simulation_start_date="2020-01-01",
                compiler="gcc-11",
            ),
            "/path/to/1081184.251218-200944": self._make_metadata(
                execution_id="1081184.251218-200944",
                simulation_start_date="2020-06-01",
                compiler="gcc-12",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        # Both runs are created as simulations
        assert result.created_count == 2
        assert len(result.simulations) == 2
        # Reference run has run_config_deltas=None
        reference = [s for s in result.simulations if s.run_config_deltas is None]
        non_reference = [
            s for s in result.simulations if s.run_config_deltas is not None
        ]
        assert len(reference) == 1
        assert len(non_reference) == 1

    def test_config_delta_stored_for_non_reference_run(self, db: Session) -> None:
        """Non-reference runs with config differences record deltas as a dict."""
        self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081185.251218-200945": self._make_metadata(
                execution_id="1081185.251218-200945",
                simulation_start_date="2020-01-01",
                compiler="gcc-11",
            ),
            "/path/to/1081186.251218-200946": self._make_metadata(
                execution_id="1081186.251218-200946",
                simulation_start_date="2020-06-01",
                compiler="gcc-12",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        # Both runs created
        assert result.created_count == 2
        # Find reference (run_config_deltas=None) and non-reference
        reference = [s for s in result.simulations if s.run_config_deltas is None]
        non_reference = [
            s for s in result.simulations if s.run_config_deltas is not None
        ]
        assert len(reference) == 1
        assert len(non_reference) == 1
        deltas = non_reference[0].run_config_deltas
        assert deltas is not None
        assert "compiler" in deltas
        assert deltas["compiler"]["reference"] == "gcc-11"
        assert deltas["compiler"]["current"] == "gcc-12"

    def test_no_delta_when_configs_identical(self, db: Session) -> None:
        """Non-reference runs with identical config have run_config_deltas=None."""
        self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081187.251218-200947": self._make_metadata(
                execution_id="1081187.251218-200947",
                simulation_start_date="2020-01-01",
            ),
            "/path/to/1081188.251218-200948": self._make_metadata(
                execution_id="1081188.251218-200948",
                simulation_start_date="2020-06-01",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        assert result.created_count == 2
        # Both simulations have run_config_deltas=None (identical configs)
        for sim in result.simulations:
            assert sim.run_config_deltas is None

    def test_different_case_names_create_separate_simulations(
        self, db: Session
    ) -> None:
        """Runs with different case_names are independent reference selections."""
        self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081189.251218-200949": self._make_metadata(
                execution_id="1081189.251218-200949",
                case_name="case_alpha",
            ),
            "/path/to/1081190.251218-200950": self._make_metadata(
                execution_id="1081190.251218-200950",
                case_name="case_beta",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        # Each case_name gets its own reference simulation
        assert result.created_count == 2
        assert result.skipped_count == 0
        # Verify Cases were created
        case_alpha = db.query(Case).filter(Case.name == "case_alpha").first()
        case_beta = db.query(Case).filter(Case.name == "case_beta").first()
        assert case_alpha is not None
        assert case_beta is not None
        case_ids = {s.case_id for s in result.simulations}
        assert case_ids == {case_alpha.id, case_beta.id}

    def test_idempotent_reingestion(self, db: Session) -> None:
        """Re-ingesting the same archive does not create duplicates."""
        machine = self._create_machine(db, "test-machine")

        # First: create a simulation in the DB to simulate prior ingestion
        user = User(
            email="test@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="case1")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1081191.251218-200951",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.UNKNOWN,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.commit()

        # Now re-ingest with the same execution_id
        mock_simulations = {
            "/path/to/1081191.251218-200951": self._make_metadata(
                execution_id="1081191.251218-200951",
                simulation_start_date="2020-01-01",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        # Duplicate detected, nothing new created
        assert result.created_count == 0
        assert result.duplicate_count == 1
        assert len(result.simulations) == 0

    def test_incremental_ingestion_new_run_adds_delta(self, db: Session) -> None:
        """A new run under an existing case records config delta."""
        machine = self._create_machine(db, "test-machine")

        # Pre-populate DB with a reference simulation
        user = User(
            email="test@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="case1")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1081192.251218-200952",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.UNKNOWN,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
            compiler="gcc-11",
        )
        db.add(sim)
        db.flush()

        # Set reference_simulation_id on the case
        assert sim.id is not None
        case.reference_simulation_id = sim.id
        db.commit()

        # Ingest archive containing the existing run plus a new one
        mock_simulations = {
            "/path/to/1081192.251218-200952": self._make_metadata(
                execution_id="1081192.251218-200952",
                simulation_start_date="2020-01-01",
                compiler="gcc-11",
            ),
            "/path/to/1081193.251218-200953": self._make_metadata(
                execution_id="1081193.251218-200953",
                simulation_start_date="2020-06-01",
                compiler="gcc-12",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        # run1 is a duplicate, run2 is new with config delta
        assert result.duplicate_count == 1
        assert result.created_count == 1
        assert len(result.simulations) == 1
        # The new run should have a config delta
        new_sim = result.simulations[0]
        assert new_sim.run_config_deltas is not None
        assert "compiler" in new_sim.run_config_deltas
        assert new_sim.run_config_deltas["compiler"]["reference"] == "gcc-11"
        assert new_sim.run_config_deltas["compiler"]["current"] == "gcc-12"

    def test_incremental_ingestion_normalizes_git_url_for_delta(
        self, db: Session
    ) -> None:
        """Equivalent SSH/HTTPS git URLs should not produce a config delta."""
        machine = self._create_machine(db, "test-machine")

        user = User(
            email="test@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="case1")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1081194.251218-200953",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.UNKNOWN,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
            git_repository_url="https://github.com/E3SM-Project/E3SM.git",
        )
        db.add(sim)
        db.flush()

        assert sim.id is not None
        case.reference_simulation_id = sim.id
        db.commit()

        mock_simulations = {
            "/path/to/1081194.251218-200956": self._make_metadata(
                execution_id="1081194.251218-200956",
                simulation_start_date="2020-06-01",
                git_repository_url="git@github.com:E3SM-Project/E3SM.git",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        assert result.created_count == 1
        assert len(result.simulations) == 1
        assert result.simulations[0].run_config_deltas is None

    def test_incremental_ingestion_persisted_simulation_type_adds_delta(
        self, db: Session
    ) -> None:
        """Persisted reference simulation_type differences are reflected in deltas."""
        machine = self._create_machine(db, "test-machine")

        user = User(
            email="test@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="case1")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1081194.251218-200954",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.PRODUCTION,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
        )
        db.add(sim)
        db.flush()

        assert sim.id is not None
        case.reference_simulation_id = sim.id
        db.commit()

        mock_simulations = {
            "/path/to/1081194.251218-200954": self._make_metadata(
                execution_id="1081194.251218-200954",
                simulation_start_date="2020-01-01",
            ),
            "/path/to/1081194.251218-200955": self._make_metadata(
                execution_id="1081194.251218-200955",
                simulation_start_date="2020-06-01",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        assert result.duplicate_count == 1
        assert result.created_count == 1
        assert len(result.simulations) == 1
        assert result.simulations[0].run_config_deltas is not None
        assert "simulation_type" in result.simulations[0].run_config_deltas
        assert result.simulations[0].run_config_deltas["simulation_type"] == {
            "reference": SimulationType.PRODUCTION.value,
            "current": SimulationType.UNKNOWN.value,
        }

    def test_same_case_name_groups_to_same_case(self, db: Session) -> None:
        """Runs with the same case_name belong to the same Case."""
        self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081195.251218-200955": self._make_metadata(
                execution_id="1081195.251218-200955",
                case_name="case1",
            ),
            "/path/to/1081196.251218-200956": self._make_metadata(
                execution_id="1081196.251218-200956",
                case_name="case1",
                simulation_start_date="2020-06-01",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        assert result.created_count == 2
        # Both simulations must share the same case_id
        case_ids = {s.case_id for s in result.simulations}
        assert len(case_ids) == 1
        # Case was created with the shared name
        case = db.query(Case).filter(Case.name == "case1").first()
        assert case is not None

    def test_different_case_name_creates_separate_cases(self, db: Session) -> None:
        """Runs with different case_name values create separate Cases."""
        self._create_machine(db, "test-machine")

        mock_simulations = {
            "/path/to/1081197.251218-200957": self._make_metadata(
                execution_id="1081197.251218-200957",
                case_name="case_X",
            ),
            "/path/to/1081198.251218-200958": self._make_metadata(
                execution_id="1081198.251218-200958",
                case_name="case_Y",
            ),
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            result = ingest_archive(Path("/tmp/a.zip"), Path("/tmp/o"), db)

        assert result.created_count == 2
        case_ids = {s.case_id for s in result.simulations}
        assert len(case_ids) == 2


class TestIngestHelpers:
    def test_get_or_create_case_sets_missing_case_group(self, db: Session) -> None:
        case = Case(name="case_group_test", case_group=None)
        db.add(case)
        db.commit()

        updated = _get_or_create_case(db, name="case_group_test", case_group="groupA")

        assert updated.id == case.id
        assert updated.case_group == "groupA"

    def test_get_or_create_case_keeps_existing_on_conflict(self, db: Session) -> None:
        case = Case(name="case_group_conflict", case_group="groupA")
        db.add(case)
        db.commit()

        with patch("app.features.ingestion.ingest.logger.warning") as mock_warning:
            updated = _get_or_create_case(
                db,
                name="case_group_conflict",
                case_group="groupB",
            )

        assert updated.id == case.id
        assert updated.case_group == "groupA"
        mock_warning.assert_called_once()

    def test_get_reference_metadata_caches_missing_persisted_reference(self) -> None:
        case = MagicMock(spec=Case)
        case.id = uuid4()
        case.reference_simulation_id = uuid4()

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None

        reference_cache: dict[str, SimulationConfigSnapshot] = {}
        persisted_reference_cache: dict[UUID, SimulationConfigSnapshot | None] = {}

        result = _get_reference_metadata_for_case(
            case=case,
            case_name="missing_reference_case",
            reference_cache=reference_cache,
            persisted_reference_cache=persisted_reference_cache,
            db=db,
        )

        assert result is None
        assert case.id in persisted_reference_cache
        assert persisted_reference_cache[case.id] is None

    def test_get_reference_metadata_uses_persisted_cache_on_second_lookup(
        self, db: Session
    ) -> None:
        machine = Machine(
            name="cache-test-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)

        user = User(
            email="cache-test@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="reference_cache_case")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1082000.260305-120000",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.UNKNOWN,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
            compiler="gcc-11",
        )
        db.add(sim)
        db.flush()

        assert sim.id is not None
        case.reference_simulation_id = sim.id
        db.commit()

        reference_cache: dict[str, SimulationConfigSnapshot] = {}
        persisted_reference_cache: dict[UUID, SimulationConfigSnapshot | None] = {}

        first = _get_reference_metadata_for_case(
            case=case,
            case_name=case.name,
            reference_cache=reference_cache,
            persisted_reference_cache=persisted_reference_cache,
            db=db,
        )
        assert first is not None
        assert first.compiler == "gcc-11"

        with patch.object(db, "query", side_effect=AssertionError):
            second = _get_reference_metadata_for_case(
                case=case,
                case_name=case.name,
                reference_cache=reference_cache,
                persisted_reference_cache=persisted_reference_cache,
                db=db,
            )
        assert second == first

    def test_parsed_snapshot_defaults_simulation_type_to_unknown(self) -> None:
        parsed = ParsedSimulation(
            execution_dir="/path/to/1082001.260305-120001",
            execution_id="1082001.260305-120001",
            case_name="case1",
            case_group=None,
            machine="machine",
            hpc_username=None,
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            campaign="campaign",
            experiment_type="historical",
            initialization_type="test",
            simulation_start_date="2020-01-01",
            simulation_end_date=None,
            run_start_date=None,
            run_end_date=None,
            compiler="gcc",
            git_repository_url="https://example.com/repo.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            status="completed",
        )

        snapshot = _build_config_snapshot(parsed)

        assert snapshot.simulation_type == SimulationType.UNKNOWN.value

    def test_persisted_snapshot_matches_config_delta_fields(self, db: Session) -> None:
        machine = Machine(
            name="projection-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)

        user = User(
            email="projection@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="projection_case")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1082002.260305-120002",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.TEST,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
            campaign="campaign",
            experiment_type="historical",
            compiler="gcc",
            git_repository_url="https://example.com/repo.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
        )
        db.add(sim)
        db.commit()

        snapshot = _build_config_snapshot(sim)

        assert snapshot.simulation_type == SimulationType.TEST.value

    def test_snapshot_normalizes_ssh_git_url_for_equality(self, db: Session) -> None:
        parsed = ParsedSimulation(
            execution_dir="/path/to/1082003.260305-120003",
            execution_id="1082003.260305-120003",
            case_name="case1",
            case_group=None,
            machine="machine",
            hpc_username=None,
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            campaign="campaign",
            experiment_type="historical",
            initialization_type="test",
            simulation_start_date="2020-01-01",
            simulation_end_date=None,
            run_start_date=None,
            run_end_date=None,
            compiler="gcc",
            git_repository_url="git@github.com:E3SM-Project/E3SM.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            status="completed",
        )

        machine = Machine(
            name="snapshot-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)

        user = User(
            email="snapshot@example.com",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="/archive",
            status=IngestionStatus.SUCCESS,
            machine_id=machine.id,
            triggered_by=user.id,
        )
        db.add(ingestion)
        db.commit()

        case = Case(name="snapshot_case")
        db.add(case)
        db.flush()

        sim = Simulation(
            case_id=case.id,
            execution_id="1082004.260305-120004",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            machine_id=machine.id,
            simulation_start_date=datetime(2020, 1, 1),
            initialization_type="test",
            status=SimulationStatus.CREATED,
            simulation_type=SimulationType.UNKNOWN,
            created_by=user.id,
            last_updated_by=user.id,
            ingestion_id=ingestion.id,
            campaign="campaign",
            experiment_type="historical",
            compiler="gcc",
            git_repository_url="https://github.com/E3SM-Project/E3SM.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
        )
        db.add(sim)
        db.commit()

        parsed_snapshot = _build_config_snapshot(parsed)
        persisted_snapshot = _build_config_snapshot(sim)

        assert parsed_snapshot == persisted_snapshot
        assert parsed_snapshot.diff(persisted_snapshot) == {}

    def test_snapshot_diff_returns_only_changed_fields(self) -> None:
        reference = SimulationConfigSnapshot(
            compset="FHIST",
            compset_alias="alias1",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            initialization_type="initial",
            compiler="gcc-11",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            git_branch="main",
            git_repository_url="https://example.com/repo.git",
            campaign="campaign1",
            experiment_type="historical",
            simulation_type=SimulationType.UNKNOWN.value,
        )
        current = SimulationConfigSnapshot(
            compset="FHIST",
            compset_alias="alias1",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            initialization_type="initial",
            compiler="gcc-12",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            git_branch="feature",
            git_repository_url="https://example.com/repo.git",
            campaign="campaign1",
            experiment_type="historical",
            simulation_type=SimulationType.UNKNOWN.value,
        )

        delta = reference.diff(current)

        assert delta == {
            "compiler": {"reference": "gcc-11", "current": "gcc-12"},
            "git_branch": {"reference": "main", "current": "feature"},
        }

    def test_simulation_create_draft_validates_by_field_name(self) -> None:
        draft = SimulationCreateDraft(
            case_id=uuid4(),
            execution_id="1082005.260305-120005",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            simulation_type=SimulationType.UNKNOWN,
            status=SimulationStatus.CREATED,
            campaign="campaign",
            experiment_type="historical",
            initialization_type="test",
            machine_id=uuid4(),
            simulation_start_date=datetime(2020, 1, 1),
            simulation_end_date=None,
            run_start_date=None,
            run_end_date=None,
            compiler="gcc",
            git_repository_url="https://example.com/repo.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            created_by=None,
            last_updated_by=None,
            hpc_username="test-user",
            run_config_deltas=None,
        )

        schema = _validate_simulation_create(draft)

        assert isinstance(schema, SimulationCreate)
        assert schema.execution_id == draft.execution_id
        assert schema.extra == {}
        assert schema.artifacts == []
        assert schema.links == []
        assert schema.run_config_deltas is None

    def test_build_simulation_create_draft_normalizes_values(self) -> None:
        parsed = ParsedSimulation(
            execution_dir="/path/to/1082006.260305-120006",
            execution_id="1082006.260305-120006",
            case_name="case1",
            case_group=None,
            machine="machine",
            hpc_username="test-user",
            compset="FHIST",
            compset_alias="test_alias",
            grid_name="grid1",
            grid_resolution="0.9x1.25",
            campaign="campaign",
            experiment_type="historical",
            initialization_type="test",
            simulation_start_date="2020-01-01",
            simulation_end_date=None,
            run_start_date="2020-01-02T03:04:05Z",
            run_end_date=None,
            compiler="gcc",
            git_repository_url="git@github.com:E3SM-Project/E3SM.git",
            git_branch="main",
            git_tag="v1.0.0",
            git_commit_hash="abc123",
            status="completed",
        )

        draft = _build_simulation_create_draft(
            parsed_simulation=parsed,
            machine_id=uuid4(),
            case_id=uuid4(),
        )

        assert draft.simulation_type == SimulationType.UNKNOWN
        assert draft.status == SimulationStatus.COMPLETED
        assert draft.git_repository_url == "https://github.com/E3SM-Project/E3SM.git"
        assert draft.simulation_start_date is not None
        assert draft.run_start_date is not None

    def test_ingest_maps_path_artifacts_for_existing_paths(
        self, db: Session, tmp_path: Path
    ) -> None:
        machine = Machine(
            name="artifact-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)

        output_path = tmp_path / "run"
        output_path.mkdir()
        archive_path = tmp_path / "archive"
        archive_path.mkdir()
        case_root = tmp_path / "case_root"
        case_root.mkdir()
        run_script = case_root / ".case.run"
        run_script.write_text("#!/bin/sh\n")
        post_script = tmp_path / "post.sh"
        post_script.write_text("#!/bin/sh\n")

        mock_simulations = {
            "/path/to/1082010.260305-120010": {
                "execution_id": "1082010.260305-120010",
                "case_name": "case-artifacts",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid1",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "status": "completed",
                "output_path": str(output_path),
                "archive_path": str(archive_path),
                "case_root": str(case_root),
                "postprocessing_script": f"{post_script} --flag value",
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            ingest_result = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

        assert len(ingest_result.simulations) == 1
        simulation = ingest_result.simulations[0]
        assert len(simulation.artifacts) == 4

        by_kind = {artifact.kind: artifact.uri for artifact in simulation.artifacts}
        assert by_kind[ArtifactKind.OUTPUT] == str(output_path)
        assert by_kind[ArtifactKind.ARCHIVE] == str(archive_path)
        assert by_kind[ArtifactKind.RUN_SCRIPT] == str(run_script)
        assert by_kind[ArtifactKind.POSTPROCESS_SCRIPT] == str(post_script)

    def test_ingest_omits_missing_path_artifacts_and_warns(
        self, db: Session, tmp_path: Path
    ) -> None:
        machine = Machine(
            name="missing-artifact-machine",
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)

        missing_output = tmp_path / "missing-run"
        missing_archive = tmp_path / "missing-archive"
        missing_case_root = tmp_path / "missing-case-root"
        missing_post_script = tmp_path / "missing-post.sh"

        mock_simulations = {
            "/path/to/1082011.260305-120011": {
                "execution_id": "1082011.260305-120011",
                "case_name": "case-missing-artifacts",
                "compset": "FHIST",
                "compset_alias": "test_alias",
                "grid_name": "grid1",
                "grid_resolution": "0.9x1.25",
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "status": "completed",
                "output_path": str(missing_output),
                "archive_path": str(missing_archive),
                "case_root": str(missing_case_root),
                "postprocessing_script": f"{missing_post_script} --foo",
            }
        }

        with patch(
            "app.features.ingestion.ingest.main_parser",
            return_value=(_parsed_simulations_from_mapping(mock_simulations), 0),
        ):
            with patch("app.features.ingestion.ingest.logger.warning") as mock_warning:
                ingest_result = ingest_archive(
                    Path("/tmp/archive.zip"), Path("/tmp/out"), db
                )

        assert len(ingest_result.simulations) == 1
        simulation = ingest_result.simulations[0]
        assert simulation.artifacts == []
        assert mock_warning.call_count >= 4
