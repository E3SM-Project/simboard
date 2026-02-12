from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from dateutil import parser as real_dateutil_parser
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.simulation.models import Simulation
from app.features.simulation.schemas import SimulationCreate, SimulationStatus
from app.features.upload.ingest import _normalize_git_url, ingest_archive
from app.features.user.models import User


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

        mock_simulations = {
            "exp_dir_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], SimulationCreate)
            assert result[0].name == "sim1"

    def test_handles_multiple_simulations(self, db: Session) -> None:
        """Test ingesting archive with multiple simulations."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "exp_2": {
                "name": "sim2",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert len(result) == 2
            assert result[0].name == "sim1"
            assert result[1].name == "sim2"

    def test_returns_empty_list_for_empty_archive(self, db: Session) -> None:
        """Test that empty archive returns empty list."""
        with patch("app.features.upload.ingest.main_parser", return_value={}):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert isinstance(result, list)
            assert len(result) == 0

    def test_accepts_string_paths(self, db: Session) -> None:
        """Test that archive_path and output_dir accept strings."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ) as mock_main_parser:
            result, _, _ = ingest_archive("/tmp/archive.zip", "/tmp/out", db)

            # Verify main_parser was called with Path objects
            assert result is not None
            mock_main_parser.assert_called_once()
            args = mock_main_parser.call_args[0]
            assert isinstance(args[0], Path)
            assert isinstance(args[1], Path)

    def test_propagates_mapping_errors(self, db: Session) -> None:
        """Test that mapping errors are propagated."""
        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser",
            return_value=mock_simulations,
        ):
            with pytest.raises(LookupError, match="nonexistent-machine"):
                ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

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

        for date_str in test_cases:
            mock_simulations = {
                "exp_1": {
                    "name": "sim1",
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
                    "group_name": None,
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
                "app.features.upload.ingest.main_parser", return_value=mock_simulations
            ):
                result, _, _ = ingest_archive(
                    Path("/tmp/archive.zip"), Path("/tmp/out"), db
                )

                assert len(result) == 1
                assert isinstance(result[0].simulation_start_date, datetime)
                assert result[0].simulation_start_date.tzinfo is not None

    def test_missing_required_fields_raise_validation_error(self, db: Session) -> None:
        """Test that missing required fields raise a validation error."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": None,
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            with pytest.raises(ValidationError):
                ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

    def test_machine_lookup_and_validation_through_public_api(
        self, db: Session
    ) -> None:
        """Test machine lookup and validation through public API.

        This test verifies that the public API correctly looks up machines
        and propagates errors for missing machines (testing _extract_simulation_key
        and machine lookup behavior).
        """
        machine = self._create_machine(db, "valid-machine")

        # Create valid simulation
        valid_mock = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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

        with patch("app.features.upload.ingest.main_parser", return_value=valid_mock):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )
            assert len(result) == 1
            assert result[0].machine_id == machine.id

        # Test with missing machine
        invalid_mock = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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

        with patch("app.features.upload.ingest.main_parser", return_value=invalid_mock):
            with pytest.raises(LookupError, match="Machine 'nonexistent'"):
                ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

    def test_timezone_aware_datetime_parsing_through_public_api(
        self, db: Session
    ) -> None:
        """Test timezone-aware datetime parsing through public API.

        This test verifies that all parsed datetimes are timezone-aware.
        """
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert len(result) == 1
            # All datetime fields should be timezone-aware
            assert result[0].simulation_start_date.tzinfo is not None
            if result[0].run_start_date:
                assert result[0].run_start_date.tzinfo is not None
            if result[0].run_end_date:
                assert result[0].run_end_date.tzinfo is not None

    def test_handles_optional_fields_through_public_api(self, db: Session) -> None:
        """Test optional field handling through public API.

        This test verifies that optional fields are properly mapped when
        provided in the metadata.
        """
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": "sim_with_optionals",
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
                "group_name": "test_group",
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert len(result) == 1
            assert result[0].experiment_type == "historical"
            assert result[0].campaign == "CMIP6"
            assert result[0].group_name == "test_group"
            assert result[0].compiler == "gcc"
            assert str(result[0].git_repository_url) == "https://github.com/test/repo"
            assert result[0].git_branch == "main"
            assert result[0].git_tag == "v1.0.0"
            assert result[0].git_commit_hash == "abc123"

    def test_skips_duplicate_simulations(self, db: Session) -> None:
        """Test that duplicate simulations are skipped during ingestion.

        This test verifies the deduplication logic by:
        1. Creating a simulation directly in the database
        2. Attempting to ingest the same simulation
        3. Verifying it's skipped and not returned
        """
        machine = self._create_machine(db, "test-machine")

        # Create a test user for created_by and last_updated_by fields
        user = User(
            id=uuid4(), email="test@example.com", is_active=True, is_superuser=False
        )
        db.add(user)
        db.commit()

        # Create a simulation directly in the database
        existing_sim = Simulation(
            name="existing_sim",
            case_name="existing_case",
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
        )
        db.add(existing_sim)
        db.commit()

        # Try to ingest the same simulation
        mock_simulations = {
            "exp_1": {
                "name": "existing_sim",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Duplicate should be skipped, result should be empty
            assert len(result) == 0

    def test_ingest_archive_counts(self, db: Session) -> None:
        """Test that summary counts reflect created and duplicate simulations."""
        machine = self._create_machine(db, "test-machine")

        user = User(
            id=uuid4(), email="test@example.com", is_active=True, is_superuser=False
        )
        db.add(user)
        db.commit()

        existing_sim = Simulation(
            name="existing_sim",
            case_name="existing_case",
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
        )
        db.add(existing_sim)
        db.commit()

        mock_simulations = {
            "exp_1": {
                "name": "existing_sim",
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
                "group_name": None,
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
            "exp_2": {
                "name": "new_sim",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, created_count, duplicate_count = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert created_count == 1
            assert duplicate_count == 1
            assert len(result) == 1
            assert result[0].name == "new_sim"

    def test_ingest_archive_empty_archive(self, db: Session) -> None:
        """Test summary counts when the archive contains no simulations."""
        with patch("app.features.upload.ingest.main_parser", return_value={}):
            result, created_count, duplicate_count = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            assert result == []
            assert created_count == 0
            assert duplicate_count == 0

    def test_handles_invalid_datetime_gracefully(self, db: Session) -> None:
        """Test that invalid datetimes are handled without raising.

        This test verifies the exception handling in _parse_datetime_field
        by testing with various invalid date formats that trigger the except block.
        """
        machine = self._create_machine(db, "test-machine")

        # Create a simulation with an invalid run_start_date
        # This will be parsed but not raise an error
        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Should succeed with optional dates as None
            assert len(result) == 1
            assert result[0].run_start_date is None
            assert result[0].run_end_date is None

    def test_parse_datetime_field_exception_handling(self, db: Session) -> None:
        """Test exception handling in _parse_datetime_field.

        This test ensures that exceptions raised during datetime parsing are logged
        and None is returned instead of propagating the error.
        """
        machine = self._create_machine(db, "test-machine")

        # Mock dateutil_parser.parse to raise an exception for specific inputs
        # This ensures we exercise the except block in _parse_datetime_field
        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
                "app.features.upload.ingest.main_parser",
                return_value=mock_simulations,
            ),
            patch(
                "app.features.upload.ingest.dateutil_parser.parse",
                side_effect=mock_parse_wrapper,
            ),
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Should succeed with run_start_date as None (exception caught and logged)
            assert len(result) == 1
            assert result[0].run_start_date is None

    def test_missing_machine_name_in_metadata(self, db: Session) -> None:
        """Test error handling when machine name is missing from metadata."""
        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            with pytest.raises(ValueError, match="Machine name is required"):
                ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

    def test_missing_simulation_start_date(self, db: Session) -> None:
        """Test error when simulation_start_date cannot be parsed."""
        machine = self._create_machine(db, "test-machine")

        mock_simulations = {
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            with pytest.raises(ValueError, match="simulation_start_date is required"):
                ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)


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
            "exp_1": {
                "name": "sim1",
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
                "group_name": None,
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
            "app.features.upload.ingest.main_parser", return_value=mock_simulations
        ):
            result, _, _ = ingest_archive(
                Path("/tmp/archive.zip"), Path("/tmp/out"), db
            )

            # Verify SSH URL was converted to HTTPS
            assert len(result) == 1
            assert str(result[0].git_repository_url) == (
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
