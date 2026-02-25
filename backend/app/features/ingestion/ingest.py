"""Module for ingesting simulation archives and mapping to database schemas.

Implements canonical run semantics for ``performance_archive`` ingestion:

* A run is "successful" only when all required metadata files are present.
* Within each case (parent directory), the **first** successful run
  (sorted by experiment-directory name) is the *canonical baseline*.
* Subsequent successful runs under the same case are compared against
  the canonical baseline.  Only configuration differences (deltas) are
  recorded in the canonical simulation's ``extra`` JSONB field; separate
  simulation records are **not** created for non-canonical runs.
* Incomplete runs (missing required files) are skipped at the parser
  level and never reach ingestion.
* Re-processing the same archive is idempotent thanks to the existing
  ``(case_name, machine_id, simulation_start_date)`` uniqueness
  constraint.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dateutil import parser as dateutil_parser
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.parser import SimulationMetadata, main_parser
from app.features.machine.models import Machine
from app.features.simulation.enums import SimulationStatus, SimulationType
from app.features.simulation.models import Simulation
from app.features.simulation.schemas import SimulationCreate

logger = _setup_custom_logger(__name__)

# Configuration fields compared when computing deltas between a
# canonical run and subsequent runs of the same case.  Timeline and
# status fields are intentionally excluded because they are expected to
# vary across successive executions of the same case.
_CONFIG_DELTA_FIELDS: frozenset[str] = frozenset(
    {
        "compset",
        "compset_alias",
        "grid_name",
        "grid_resolution",
        "initialization_type",
        "compiler",
        "git_tag",
        "git_commit_hash",
        "git_branch",
        "git_repository_url",
        "campaign",
        "experiment_type",
        "group_name",
    }
)


@dataclass
class IngestArchiveResult:
    """
    Structured result of an archive ingestion operation.

    This object encapsulates the outcome of parsing and validating a
    simulation archive prior to persistence. It includes successfully
    mapped simulations, duplicate counts, and per-experiment errors.

    Attributes
    ----------
    simulations : list[SimulationCreate]
        Collection of simulation schema objects successfully parsed and
        validated from the archive.
    created_count : int
        Number of new simulations eligible for creation.
    duplicate_count : int
        Number of simulations skipped due to existing records in the database.
    skipped_count : int
        Number of non-canonical runs whose configuration deltas were
        recorded on the canonical simulation rather than being ingested
        as separate records.
    errors : list[dict[str, str]]
        List of ingestion errors encountered during processing. Each entry
        contains keys such as ``exp_dir``, ``error_type``, and ``error``,
        describing the failed experiment and associated exception details.
    """

    simulations: list[SimulationCreate]
    created_count: int
    duplicate_count: int
    skipped_count: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> IngestArchiveResult:
    """Ingest a simulation archive and return summary counts.

    Implements canonical run semantics:

    * Parsed simulations are grouped by ``case_name``.
    * The first successful run per case (in sorted experiment-directory
      order) is treated as the canonical baseline and mapped to a
      ``SimulationCreate`` record.
    * Subsequent successful runs for the same case are compared against
      the canonical baseline; only configuration differences are stored
      in the canonical simulation's ``extra["run_config_deltas"]`` list.
    * Duplicate detection is based on the composite key
      ``(case_name, machine_id, simulation_start_date)``.

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
    IngestArchiveResult
        Dataclass containing list of SimulationCreate objects, counts of created
        and duplicate simulations, and any errors encountered during processing.

    Raises
    ------
    ValueError
        If required fields are missing or cannot be parsed.
    LookupError
        If a machine name from the archive cannot be found in the database.
    ValidationError
        If metadata fails schema validation.
    """
    archive_path_resolved = (
        Path(archive_path) if isinstance(archive_path, str) else archive_path
    )
    output_dir_resolved = (
        Path(output_dir) if isinstance(output_dir, str) else output_dir
    )

    all_simulations = main_parser(archive_path_resolved, output_dir_resolved)

    if not all_simulations:
        logger.warning(f"No simulations found in archive: {archive_path_resolved}")

        return IngestArchiveResult(
            simulations=[], created_count=0, duplicate_count=0, skipped_count=0
        )

    # Group simulations by case_name for canonical run selection.
    # The dict preserves insertion order (Python 3.7+), and main_parser
    # returns experiment dirs sorted within each case group, so the
    # first entry per case_name is the canonical candidate.
    case_groups: dict[str, list[tuple[str, SimulationMetadata]]] = defaultdict(list)

    for exp_dir, metadata in all_simulations.items():
        case_name = metadata.get("case_name") or metadata.get("name") or "unknown"
        case_groups[case_name].append((exp_dir, metadata))

    simulations: list[SimulationCreate] = []
    duplicate_count = 0
    skipped_count = 0
    errors: list[dict[str, str]] = []

    for case_name, runs in case_groups.items():
        canonical_metadata: SimulationMetadata | None = None
        canonical_exp_dir: str | None = None

        for exp_dir, metadata in runs:
            try:
                case_key, machine_id, simulation_start_date = (
                    _extract_simulation_key(metadata, db)
                )

                existing_sim = _find_existing_simulation(
                    db, case_key, machine_id, simulation_start_date
                )
                if existing_sim:
                    logger.info(
                        f"Simulation already exists in database with "
                        f"case_name='{case_key}', machine_id={machine_id}, "
                        f"simulation_start_date={simulation_start_date}. "
                        f"Skipping duplicate from {exp_dir}."
                    )
                    duplicate_count += 1

                    # If the existing sim is the canonical for this case,
                    # record it so subsequent runs can compute deltas.
                    if canonical_metadata is None:
                        canonical_metadata = metadata
                        canonical_exp_dir = exp_dir
                    continue

                if canonical_metadata is None:
                    # First successful run → canonical baseline.
                    canonical_metadata = metadata
                    canonical_exp_dir = exp_dir

                    sim_create = _map_metadata_to_schema(metadata, db, machine_id)
                    simulations.append(sim_create)
                    logger.info(
                        f"Mapped canonical simulation from {exp_dir}: "
                        f"{metadata.get('name')}"
                    )
                else:
                    # Subsequent successful run → record config delta only.
                    delta = _compute_config_delta(canonical_metadata, metadata)
                    if delta:
                        logger.info(
                            f"Non-canonical run in '{exp_dir}' has config "
                            f"differences from canonical '{canonical_exp_dir}': "
                            f"{list(delta.keys())}"
                        )
                        # Attach the delta to the canonical simulation's
                        # extra field so it can be persisted.
                        _attach_config_delta(
                            simulations, canonical_metadata, exp_dir, delta
                        )
                    else:
                        logger.info(
                            f"Non-canonical run in '{exp_dir}' has identical "
                            f"configuration to canonical '{canonical_exp_dir}'."
                        )
                    skipped_count += 1

            except (ValueError, LookupError, ValidationError) as e:
                logger.error(f"Failed to process simulation from {exp_dir}: {e}")
                errors.append(
                    {
                        "exp_dir": str(exp_dir),
                        "error_type": type(e).__name__,
                        "error": str(e),
                    }
                )
                continue

    result = IngestArchiveResult(
        simulations=simulations,
        created_count=len(simulations),
        duplicate_count=duplicate_count,
        skipped_count=skipped_count,
        errors=errors,
    )
    return result


def _compute_config_delta(
    canonical: SimulationMetadata,
    other: SimulationMetadata,
) -> dict[str, dict[str, str | None]]:
    """Compare two run metadata dicts and return configuration differences.

    Only the fields in :data:`_CONFIG_DELTA_FIELDS` are compared.
    Timeline, status, and other per-run fields are intentionally
    excluded because they are expected to vary across successive
    executions of the same case.

    Parameters
    ----------
    canonical : SimulationMetadata
        The canonical (baseline) run metadata.
    other : SimulationMetadata
        The subsequent run metadata to compare against.

    Returns
    -------
    dict[str, dict[str, str | None]]
        Mapping of field name → ``{"canonical": ..., "current": ...}``
        for every field that differs.  Empty dict when runs are
        identical.
    """
    delta: dict[str, dict[str, str | None]] = {}

    for key in _CONFIG_DELTA_FIELDS:
        canonical_val = canonical.get(key)
        other_val = other.get(key)
        if canonical_val != other_val:
            delta[key] = {"canonical": canonical_val, "current": other_val}

    return delta


def _attach_config_delta(
    simulations: list[SimulationCreate],
    canonical_metadata: SimulationMetadata,
    exp_dir: str,
    delta: dict[str, dict[str, str | None]],
) -> None:
    """Attach a config delta to the canonical simulation's ``extra`` field.

    The delta is appended to ``extra["run_config_deltas"]`` so that all
    differences from non-canonical runs are preserved on the canonical
    simulation record.

    Parameters
    ----------
    simulations : list[SimulationCreate]
        The list of ingested simulations; the last entry matching the
        canonical metadata is updated.
    canonical_metadata : SimulationMetadata
        Metadata of the canonical run (used to locate the correct
        SimulationCreate in *simulations*).
    exp_dir : str
        Experiment directory of the non-canonical run.
    delta : dict[str, dict[str, str | None]]
        Configuration differences to record.
    """
    # Find the canonical SimulationCreate (the one whose case_name matches).
    canonical_case = canonical_metadata.get("case_name")
    for sim in simulations:
        if sim.case_name == canonical_case:
            if sim.extra is None:
                sim.extra = {}
            deltas_list = sim.extra.setdefault("run_config_deltas", [])
            deltas_list.append({"exp_dir": exp_dir, "deltas": delta})
            break


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
            # Remove 'git@'.
            host_and_path = url[4:]
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
    simulation_end_date = _parse_datetime_field(metadata.get("simulation_end_date"))

    run_start_date = _parse_datetime_field(metadata.get("run_start_date"))
    run_end_date = _parse_datetime_field(metadata.get("run_end_date"))

    git_repository_url = _normalize_git_url(metadata.get("git_repository_url"))
    simulation_type = _normalize_simulation_type(metadata.get("simulation_type"))
    status = _normalize_simulation_status(metadata.get("status"))

    # Map metadata to schema; Pydantic will validate required fields
    # Note: SimulationCreate uses CamelInBaseModel which expects camelCase field names
    result = SimulationCreate.model_validate(
        {
            # Required identification fields
            "name": metadata.get("name"),
            "caseName": metadata.get("case_name"),
            # Required configuration fields
            "compset": metadata.get("compset"),
            "compsetAlias": metadata.get("compset_alias"),
            "gridName": metadata.get("grid_name"),
            "gridResolution": metadata.get("grid_resolution"),
            # Required status fields with sensible defaults
            "simulationType": simulation_type,
            "status": status,
            "initializationType": metadata.get("initialization_type"),
            "machineId": machine_id,
            "simulationStartDate": simulation_start_date,
            "simulationEndDate": simulation_end_date,
            # Optional experiment classification
            "experimentType": metadata.get("experiment_type"),
            "campaign": metadata.get("campaign"),
            "groupName": metadata.get("group_name"),
            # Optional timing fields
            "runStartDate": run_start_date,
            "runEndDate": run_end_date,
            # Optional software/environment fields
            "compiler": metadata.get("compiler"),
            "gitRepositoryUrl": git_repository_url,
            "gitBranch": metadata.get("git_branch"),
            "gitTag": metadata.get("git_tag"),
            "gitCommitHash": metadata.get("git_commit_hash"),
            # Note: created_by and last_updated_by are set to None since archive
            # metadata contains local usernames that cannot be reliably mapped to
            # database user UUIDs. The API endpoint will set these values based on
            # the authenticated user who uploaded the archive.
            "createdBy": None,
            "lastUpdatedBy": None,
            "hpcUsername": metadata.get("hpc_username"),
        }
    )

    return result


def _normalize_simulation_type(value: str | None) -> SimulationType:
    """Return a valid SimulationType enum value with UNKNOWN fallback."""
    if not value:
        return SimulationType.UNKNOWN

    normalized = value.strip()
    if not normalized:
        return SimulationType.UNKNOWN

    try:
        return SimulationType(normalized)
    except ValueError:
        try:
            return SimulationType[normalized.upper()]
        except KeyError:
            logger.warning(
                "Unknown simulation_type '%s'; defaulting to '%s'.",
                value,
                SimulationType.UNKNOWN.value,
            )
            return SimulationType.UNKNOWN


def _normalize_simulation_status(value: str | None) -> SimulationStatus:
    """Return a valid SimulationStatus enum value with CREATED fallback."""
    if not value:
        return SimulationStatus.CREATED

    normalized = value.strip()
    if not normalized:
        return SimulationStatus.CREATED

    try:
        return SimulationStatus(normalized)
    except ValueError:
        try:
            return SimulationStatus[normalized.upper()]
        except KeyError:
            logger.warning(
                "Unknown status '%s'; defaulting to '%s'.",
                value,
                SimulationStatus.CREATED.value,
            )
            return SimulationStatus.CREATED


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
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse date '{value}': {e}")

        return None
