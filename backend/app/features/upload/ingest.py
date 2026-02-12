"""Module for ingesting simulation archives and mapping to database schemas."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dateutil import parser as dateutil_parser
from sqlalchemy.orm import Session

from app.core.logger import _setup_custom_logger
from app.features.machine.models import Machine
from app.features.simulation.schemas import SimulationCreate, SimulationStatus
from app.features.upload.parsers.parser import (
    SimulationMetadata,
    main_parser,
)

if TYPE_CHECKING:
    pass

logger = _setup_custom_logger(__name__)


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> list[SimulationCreate]:
    """
    Ingest a simulation archive and map parsed metadata to SimulationCreate schemas.

    This function orchestrates the archive extraction and parsing, then maps the
    extracted metadata to SimulationCreate schema objects with proper type conversions
    and database lookups for machine IDs.

    Parameters
    ----------
    archive_path : Path | str
        Path to the archive file to ingest (.zip or .tar.gz).
    output_dir : Path | str
        Directory where extracted files will be stored.
    db : Session
        SQLAlchemy database session for looking up machines.

    Returns
    -------
    list[SimulationCreate]
        List of SimulationCreate schema objects ready for database insertion.

    Raises
    ------
    ValueError
        If archive format is unsupported or no experiment directories found.
    LookupError
        If a machine name from the archive cannot be found in the database.
    """
    archive_path = Path(archive_path) if isinstance(archive_path, str) else archive_path
    output_dir = Path(output_dir) if isinstance(output_dir, str) else output_dir

    # Parse the archive to extract metadata
    all_simulations = main_parser(archive_path, output_dir)

    if not all_simulations:
        logger.warning(f"No simulations found in archive: {archive_path}")
        return []

    # Map each simulation metadata to SimulationCreate schema
    simulations = []
    for exp_dir, metadata in all_simulations.items():
        try:
            sim_create = _map_metadata_to_schema(metadata, db)
            simulations.append(sim_create)
            logger.info(f"Mapped simulation from {exp_dir}: {metadata.get('name')}")
        except (ValueError, LookupError) as e:
            logger.error(f"Failed to map simulation from {exp_dir}: {e}")
            raise

    return simulations


def _map_metadata_to_schema(
    metadata: SimulationMetadata,
    db: Session,
) -> SimulationCreate:
    """
    Map parser metadata to SimulationCreate schema with type conversions.

    Parameters
    ----------
    metadata : SimulationMetadata
        Dictionary of parsed simulation metadata with string values.
    db : Session
        SQLAlchemy database session for machine lookups.

    Returns
    -------
    SimulationCreate
        Schema object ready for database insertion.

    Raises
    ------
    ValueError
        If required field is missing or cannot be parsed.
    LookupError
        If machine name cannot be found in database.
    """
    # Extract machine_id from machine name using database lookup
    machine_name = metadata.get("machine")
    if not machine_name:
        raise ValueError("Machine name is required but not found in metadata")

    machine = db.query(Machine).filter(Machine.name == machine_name).first()
    if not machine:
        raise LookupError(
            f"Machine '{machine_name}' not found in database. "
            "Please ensure the machine exists before uploading."
        )
    machine_id = machine.id

    # Parse datetime fields, handling various formats
    def parse_datetime_field(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            # Try parsing with dateutil for flexibility
            dt = dateutil_parser.parse(value)
            # Ensure timezone-aware (UTC if not specified)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
            return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse date '{value}': {e}")
            return None

    simulation_start_date = parse_datetime_field(metadata.get("simulation_start_date"))
    if not simulation_start_date:
        raise ValueError("simulation_start_date is required but could not be parsed")

    run_start_date = parse_datetime_field(metadata.get("run_start_date"))
    run_end_date = parse_datetime_field(metadata.get("run_end_date"))

    # Map metadata to schema, providing sensible defaults for required fields
    return SimulationCreate(
        # Required identification fields
        name=metadata.get("name") or metadata.get("case_name") or "simulation",
        case_name=metadata.get("case_name") or metadata.get("name") or "unknown",
        # Required configuration fields
        compset=metadata.get("compset") or "unknown",
        compset_alias=metadata.get("compset_alias"),
        grid_name=metadata.get("grid_name") or "unknown",
        grid_resolution=metadata.get("grid_resolution"),
        # Required status fields with sensible defaults
        simulation_type=metadata.get("simulation_type") or "e3sm_simulation",
        status=SimulationStatus.CREATED,
        initialization_type=metadata.get("initialization_type") or "unknown",
        machine_id=machine_id,
        simulation_start_date=simulation_start_date,
        # Optional experiment classification
        experiment_type=metadata.get("experiment_type"),
        campaign=metadata.get("campaign"),
        group_name=metadata.get("group_name"),
        # Optional timing fields
        run_start_date=run_start_date,
        run_end_date=run_end_date,
        # Optional software/environment fields
        compiler=metadata.get("compiler"),
        git_repository_url=metadata.get("git_repository_url"),
        git_branch=metadata.get("git_branch"),
        git_tag=metadata.get("git_tag"),
        git_commit_hash=metadata.get("git_commit_hash"),
        # Optional provenance fields
        created_by=metadata.get("created_by"),
        last_updated_by=metadata.get("last_updated_by"),
    )
