"""Tests for the ingest module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.simulation.schemas import SimulationCreate, SimulationStatus
from app.features.upload.ingest import (
    _map_metadata_to_schema,
    ingest_archive,
)
from app.features.upload.parsers.parser import SimulationMetadata


class TestMapMetadataToSchema:
    """Tests for the _map_metadata_to_schema helper function."""

    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        """Create a test machine in the database.

        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        name : str
            Machine name.

        Returns
        -------
        Machine
            Created machine instance.
        """
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

    def test_maps_required_fields_successfully(self, db: Session) -> None:
        """Test mapping with all required fields present."""
        # Create a test machine
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": "test_sim",
            "case_name": "test_case",
            "compset": "FHIST",
            "compset_alias": "FHIST_f09_fe",
            "grid_name": "f09_fe",
            "grid_resolution": "0.9x1.25",
            "machine": machine.name,
            "simulation_start_date": "2020-01-01 00:00:00",
            "initialization_type": "BRANCH",
            "simulation_type": "historical",
            "status": "CREATED",
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

        result = _map_metadata_to_schema(metadata, db)

        assert isinstance(result, SimulationCreate)
        assert result.name == "test_sim"
        assert result.case_name == "test_case"
        assert result.compset == "FHIST"
        assert result.machine_id == machine.id
        assert result.simulation_type == "historical"
        assert result.status == SimulationStatus.CREATED
        assert result.initialization_type == "BRANCH"
        assert isinstance(result.simulation_start_date, datetime)

    def test_uses_defaults_for_missing_required_fields(self, db: Session) -> None:
        """Test that sensible defaults are applied for missing required fields."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": None,
            "case_name": None,
            "compset": None,
            "compset_alias": None,
            "grid_name": None,
            "grid_resolution": None,
            "machine": machine.name,
            "simulation_start_date": "2020-01-01",
            "initialization_type": None,
            "simulation_type": None,
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

        result = _map_metadata_to_schema(metadata, db)

        # Check defaults are applied
        assert result.name == "simulation"
        assert result.case_name == "unknown"
        assert result.compset == "unknown"
        assert result.grid_name == "unknown"
        assert result.simulation_type == "e3sm_simulation"
        assert result.status == SimulationStatus.CREATED
        assert result.initialization_type == "unknown"

    def test_maps_optional_fields_when_present(self, db: Session) -> None:
        """Test mapping of optional fields when provided."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": "sim_with_optionals",
            "case_name": "case_with_optionals",
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

        result = _map_metadata_to_schema(metadata, db)

        assert result.experiment_type == "historical"
        assert result.campaign == "CMIP6"
        assert result.group_name == "test_group"
        assert result.compiler == "gcc"
        # git_repository_url is a HttpUrl object, so compare as string
        assert str(result.git_repository_url) == "https://github.com/test/repo"
        assert result.git_branch == "main"
        assert result.git_tag == "v1.0.0"
        assert result.git_commit_hash == "abc123"
        # Note: created_by and last_updated_by are intentionally set to None
        # because archive metadata contains local usernames that cannot be
        # reliably mapped to database user UUIDs
        assert result.created_by is None
        assert result.last_updated_by is None
        assert isinstance(result.run_start_date, datetime)
        assert isinstance(result.run_end_date, datetime)

    def test_parses_various_datetime_formats(self, db: Session) -> None:
        """Test that various datetime formats are parsed correctly."""
        machine = self._create_machine(db, "test-machine")

        test_cases = [
            "2020-01-01",
            "2020-01-01 12:30:45",
            "2020-01-01T12:30:45",
            "01/01/2020",
            "Jan 1, 2020",
        ]

        for date_str in test_cases:
            metadata: SimulationMetadata = {
                "name": "test",
                "case_name": "test",
                "compset": "test",
                "compset_alias": None,
                "grid_name": "test",
                "grid_resolution": None,
                "machine": machine.name,
                "simulation_start_date": date_str,
                "initialization_type": "test",
                "simulation_type": None,
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

            result = _map_metadata_to_schema(metadata, db)

            assert isinstance(result.simulation_start_date, datetime), (
                f"Failed to parse: {date_str}"
            )
            assert result.simulation_start_date.tzinfo is not None, (
                f"Timezone not set for: {date_str}"
            )

    def test_ensures_timezone_aware_datetimes(self, db: Session) -> None:
        """Test that parsed datetimes are timezone-aware."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": "test",
            "case_name": "test",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": machine.name,
            "simulation_start_date": "2020-01-01",
            "initialization_type": "test",
            "simulation_type": None,
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

        result = _map_metadata_to_schema(metadata, db)

        # All datetime fields should be timezone-aware
        assert result.simulation_start_date.tzinfo is not None
        if result.run_start_date:
            assert result.run_start_date.tzinfo is not None
        if result.run_end_date:
            assert result.run_end_date.tzinfo is not None

    def test_raises_error_on_missing_machine_name(self, db: Session) -> None:
        """Test ValueError raised when machine name is missing."""
        metadata: SimulationMetadata = {
            "name": "test",
            "case_name": "test",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": None,
            "simulation_start_date": "2020-01-01",
            "initialization_type": "test",
            "simulation_type": None,
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

        with pytest.raises(ValueError, match="Machine name is required"):
            _map_metadata_to_schema(metadata, db)

    def test_raises_error_on_missing_machine_in_database(self, db: Session) -> None:
        """Test LookupError raised when machine not found in database."""
        metadata: SimulationMetadata = {
            "name": "test",
            "case_name": "test",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": "nonexistent-machine",
            "simulation_start_date": "2020-01-01",
            "initialization_type": "test",
            "simulation_type": None,
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

        with pytest.raises(LookupError, match="Machine 'nonexistent-machine'"):
            _map_metadata_to_schema(metadata, db)

    def test_raises_error_on_invalid_simulation_start_date(self, db: Session) -> None:
        """Test ValueError raised when simulation_start_date cannot be parsed."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": "test",
            "case_name": "test",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": machine.name,
            "simulation_start_date": None,
            "initialization_type": "test",
            "simulation_type": None,
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

        with pytest.raises(ValueError, match="simulation_start_date is required"):
            _map_metadata_to_schema(metadata, db)

    def test_handles_empty_optional_dates_gracefully(self, db: Session) -> None:
        """Test that empty or None optional dates don't cause errors."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": "test",
            "case_name": "test",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": machine.name,
            "simulation_start_date": "2020-01-01",
            "initialization_type": "test",
            "simulation_type": None,
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

        result = _map_metadata_to_schema(metadata, db)

        assert result.run_start_date is None
        assert result.run_end_date is None

    def test_uses_fallback_name_from_case_name(self, db: Session) -> None:
        """Test that case_name is used as fallback for name field."""
        machine = self._create_machine(db, "test-machine")

        metadata: SimulationMetadata = {
            "name": None,
            "case_name": "fallback_case",
            "compset": "test",
            "compset_alias": None,
            "grid_name": "test",
            "grid_resolution": None,
            "machine": machine.name,
            "simulation_start_date": "2020-01-01",
            "initialization_type": "test",
            "simulation_type": None,
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

        result = _map_metadata_to_schema(metadata, db)

        assert result.name == "fallback_case"


class TestIngestArchive:
    """Tests for the ingest_archive main function."""

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
                "compset_alias": None,
                "grid_name": "grid1",
                "grid_resolution": None,
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": None,
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
            result = ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

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
                "compset_alias": None,
                "grid_name": "grid1",
                "grid_resolution": None,
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": None,
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
                "compset_alias": None,
                "grid_name": "grid2",
                "grid_resolution": None,
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": None,
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
            "app.features.upload.ingest.main_parser",
            return_value=mock_simulations,
        ):
            result = ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

            assert len(result) == 2
            assert result[0].name == "sim1"
            assert result[1].name == "sim2"

    def test_returns_empty_list_for_empty_archive(self, db: Session) -> None:
        """Test that empty archive returns empty list."""
        with patch("app.features.upload.ingest.main_parser", return_value={}):
            result = ingest_archive(Path("/tmp/archive.zip"), Path("/tmp/out"), db)

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
                "compset_alias": None,
                "grid_name": "grid",
                "grid_resolution": None,
                "machine": machine.name,
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": None,
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
        ) as mock_main_parser:
            result = ingest_archive("/tmp/archive.zip", "/tmp/out", db)

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
                "compset_alias": None,
                "grid_name": "grid",
                "grid_resolution": None,
                "machine": "nonexistent-machine",
                "simulation_start_date": "2020-01-01",
                "initialization_type": "test",
                "simulation_type": None,
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
