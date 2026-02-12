"""Module for ingesting simulation archives and mapping to database schemas."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from dateutil import parser as dateutil_parser
from sqlalchemy.orm import Session

from app.core.logger import _setup_custom_logger
from app.features.machine.models import Machine
from app.features.simulation.models import Simulation
from app.features.simulation.schemas import SimulationCreate, SimulationStatus
from app.features.upload.parsers.parser import SimulationMetadata, main_parser

logger = _setup_custom_logger(__name__)


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> list[SimulationCreate]:
    """
    Ingest a simulation archive and map parsed metadata to SimulationCreate
    schemas.

    This function orchestrates the archive extraction and parsing, then maps the
    extracted metadata to SimulationCreate schema objects with proper type
    conversions and database lookups for machine IDs. It implements
    deduplication by checking if a simulation with the same (case_name,
    machine_id, simulation_start_date) already exists in the database.
    Duplicate simulations are skipped.

    Parameters
    ----------
    archive_path : Path | str
        Path to the archive file to ingest (.zip or .tar.gz).
    output_dir : Path | str
        Directory where extracted files will be stored.
    db : Session
        SQLAlchemy database session for machine and simulation lookups.

    Returns
    -------
    list[SimulationCreate]
        List of SimulationCreate schema objects ready for database insertion.
        Duplicates are excluded and logged.

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
            # Extract deduplication key
            case_name, machine_id, simulation_start_date = _extract_simulation_key(
                metadata, db
            )

            # Check for existing simulation (deduplication)
            existing_sim = _find_existing_simulation(
                db, case_name, machine_id, simulation_start_date
            )
            if existing_sim:
                logger.info(
                    f"Simulation already exists in database with "
                    f"case_name='{case_name}', machine_id={machine_id}, "
                    f"simulation_start_date={simulation_start_date}. "
                    f"Skipping duplicate from {exp_dir}."
                )
                continue

            # Map metadata to schema, passing already-extracted machine_id
            sim_create = _map_metadata_to_schema(metadata, db, machine_id)
            simulations.append(sim_create)
            logger.info(f"Mapped new simulation from {exp_dir}: {metadata.get('name')}")
        except (ValueError, LookupError) as e:
            logger.error(f"Failed to process simulation from {exp_dir}: {e}")
            raise

    return simulations


def ingest_archive_summary(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> tuple[list[SimulationCreate], int, int]:
    """Ingest a simulation archive and return summary counts.

    Returns
    -------
    tuple[list[SimulationCreate], int, int]
        (created_simulations, created_count, skipped_count).
    """
    archive_path = Path(archive_path) if isinstance(archive_path, str) else archive_path
    output_dir = Path(output_dir) if isinstance(output_dir, str) else output_dir

    all_simulations = main_parser(archive_path, output_dir)

    if not all_simulations:
        logger.warning(f"No simulations found in archive: {archive_path}")
        return [], 0, 0

    simulations = []
    skipped_count = 0
    for exp_dir, metadata in all_simulations.items():
        try:
            case_name, machine_id, simulation_start_date = _extract_simulation_key(
                metadata, db
            )

            existing_sim = _find_existing_simulation(
                db, case_name, machine_id, simulation_start_date
            )
            if existing_sim:
                logger.info(
                    f"Simulation already exists in database with "
                    f"case_name='{case_name}', machine_id={machine_id}, "
                    f"simulation_start_date={simulation_start_date}. "
                    f"Skipping duplicate from {exp_dir}."
                )
                skipped_count += 1
                continue

            sim_create = _map_metadata_to_schema(metadata, db, machine_id)
            simulations.append(sim_create)
            logger.info(f"Mapped new simulation from {exp_dir}: {metadata.get('name')}")
        except (ValueError, LookupError) as e:
            logger.error(f"Failed to process simulation from {exp_dir}: {e}")
            raise

    return simulations, len(simulations), skipped_count


def _extract_simulation_key(
    metadata: SimulationMetadata, db: Session
) -> tuple[str, UUID, datetime]:
    """Extract deduplication key components from metadata.

    Parameters
    ----------
    metadata : SimulationMetadata
        Parsed simulation metadata.
    db : Session
        SQLAlchemy database session for machine lookup.

    Returns
    -------
    tuple[str, UUID, datetime]
        Case name, machine ID, and simulation start date.

    Raises
    ------
    ValueError
        If required fields are missing or cannot be parsed.
    LookupError
        If machine name cannot be found in database.
    """
    # Get machine_id
    machine_name = metadata.get("machine")
    if not machine_name:
        raise ValueError("Machine name is required but not found in metadata")

    machine = db.query(Machine).filter(Machine.name == machine_name).first()
    if not machine:
        raise LookupError(
            f"Machine '{machine_name}' not found in database. "
            "Please ensure the machine exists before uploading."
        )

    # Parse simulation_start_date
    simulation_start_date = _parse_datetime_field(metadata.get("simulation_start_date"))
    if not simulation_start_date:
        raise ValueError("simulation_start_date is required but could not be parsed")

    # Get case_name (fallback to name if not available)
    case_name = metadata.get("case_name") or metadata.get("name") or "unknown"

    return case_name, machine.id, simulation_start_date


def _find_existing_simulation(
    db: Session, case_name: str, machine_id: UUID, simulation_start_date: datetime
) -> Simulation | None:
    """Find existing simulation using deduplication composite key.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session.
    case_name : str
        Case name to search for.
    machine_id : UUID
        Machine ID to search for.
    simulation_start_date : datetime
        Simulation start date to search for.

    Returns
    -------
    Simulation | None
        Matching simulation if found, None otherwise.
    """
    return (
        db.query(Simulation)
        .filter(
            Simulation.case_name == case_name,
            Simulation.machine_id == machine_id,
            Simulation.simulation_start_date == simulation_start_date,
        )
        .first()
    )


def _normalize_git_url(url: str | None) -> str | None:
    """Convert SSH git URL to HTTPS format.

    Parameters
    ----------
    url : str | None
        Git URL (SSH or HTTPS format).

    Returns
    -------
    str | None
        Normalized HTTPS URL or None if input is None/empty.

    Examples
    --------
    >>> _normalize_git_url("git@github.com:E3SM-Project/E3SM.git")
    'https://github.com/E3SM-Project/E3SM.git'

    >>> _normalize_git_url("https://github.com/E3SM-Project/E3SM.git")
    'https://github.com/E3SM-Project/E3SM.git'

    >>> _normalize_git_url(None)
    None
    """
    if not url:
        return None

    # If already HTTPS, return as-is
    if url.startswith("https://") or url.startswith("http://"):
        return url

    # Convert SSH format: git@github.com:owner/repo.git → https://github.com/owner/repo.git
    if url.startswith("git@"):
        try:
            # Extract host and path from git@host:path format
            host_and_path = url[4:]  # Remove 'git@'
            host, path = host_and_path.split(":", 1)
            return f"https://{host}/{path}"
        except ValueError:
            logger.warning(f"Could not normalize git URL: {url}")
            return url

    # For any other format, return as-is
    return url


def _map_metadata_to_schema(
    metadata: SimulationMetadata, db: Session, machine_id: UUID
) -> SimulationCreate:
    """Map parser metadata to SimulationCreate schema with type conversions.

    Parameters
    ----------
    metadata : SimulationMetadata
        Dictionary of parsed simulation metadata with string values.
    db : Session
        SQLAlchemy database session (used for validation context).
    machine_id : UUID
        Pre-extracted machine ID from _extract_simulation_key.

    Returns
    -------
    SimulationCreate
        Schema object ready for database insertion.

    Raises
    ------
    ValueError
        If simulation_start_date cannot be parsed.
    """
    # Parse datetime fields using the shared utility function
    # Note: simulation_start_date is already validated in _extract_simulation_key()
    simulation_start_date = _parse_datetime_field(metadata.get("simulation_start_date"))

    run_start_date = _parse_datetime_field(metadata.get("run_start_date"))
    run_end_date = _parse_datetime_field(metadata.get("run_end_date"))

    # Map metadata to schema, providing sensible defaults for required fields
    # Note: SimulationCreate uses CamelInBaseModel which expects camelCase field names
    return SimulationCreate.model_validate(
        {
            # Required identification fields
            "name": metadata.get("name") or metadata.get("case_name") or "simulation",
            "caseName": (
                metadata.get("case_name") or metadata.get("name") or "unknown"
            ),
            # Required configuration fields
            "compset": metadata.get("compset") or "unknown",
            "compsetAlias": metadata.get("compset_alias") or "unknown",
            "gridName": metadata.get("grid_name") or "unknown",
            "gridResolution": metadata.get("grid_resolution") or "unknown",
            # Required status fields with sensible defaults
            "simulationType": metadata.get("simulation_type") or "e3sm_simulation",
            "status": SimulationStatus.CREATED,
            "initializationType": metadata.get("initialization_type") or "unknown",
            "machineId": machine_id,
            "simulationStartDate": simulation_start_date,
            # Optional experiment classification
            "experimentType": metadata.get("experiment_type"),
            "campaign": metadata.get("campaign"),
            "groupName": metadata.get("group_name"),
            # Optional timing fields
            "runStartDate": run_start_date,
            "runEndDate": run_end_date,
            # Optional software/environment fields
            "compiler": metadata.get("compiler"),
            "gitRepositoryUrl": _normalize_git_url(metadata.get("git_repository_url")),
            "gitBranch": metadata.get("git_branch"),
            "gitTag": metadata.get("git_tag"),
            "gitCommitHash": metadata.get("git_commit_hash"),
            # Note: created_by and last_updated_by are set to None since archive
            # metadata contains local usernames that cannot be reliably mapped to
            # database user UUIDs. The API endpoint will set these values based on
            # the authenticated user who uploaded the archive.
            "createdBy": None,
            "lastUpdatedBy": None,
        }
    )


def _parse_datetime_field(value: str | None) -> datetime | None:
    """Parse datetime from string with flexible format handling.

    Parameters
    ----------
    value : str | None
        Datetime string to parse.

    Returns
    -------
    datetime | None
        Parsed datetime (UTC-aware) or None if parsing fails.
    """
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
