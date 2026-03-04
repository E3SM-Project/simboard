"""Module for ingesting simulation archives and mapping to database schemas.

Implements canonical run semantics for ``performance_archive`` ingestion:

* A run is "successful" only when all required metadata files are present.
* ``CASE_HASH`` from ``env_case.xml`` is the **mandatory** identity for
  Case grouping — no fallback to directory name or other heuristics.
* Within each case, the **first** successful run is the *canonical
  baseline*.
* Each successful run creates its own ``Simulation`` record linked to
  a ``Case`` via ``case_id``.
* The canonical simulation has ``run_config_deltas = None``.
* Non-canonical simulations store a single dict of config differences
  against the canonical baseline.
* Incomplete runs (missing required files) are skipped at the parser
  level and never reach ingestion.
* Re-processing the same archive is idempotent thanks to the
  ``execution_id`` uniqueness constraint.
"""

import os
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
from app.features.simulation.models import Case, Simulation
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
        Number of incomplete runs that were skipped at the parser level.
    errors : list[dict[str, str]]
        List of ingestion errors encountered during processing.
    """

    simulations: list[SimulationCreate]
    created_count: int
    duplicate_count: int
    skipped_count: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def ingest_archive(  # noqa: C901
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> IngestArchiveResult:
    """Ingest a simulation archive and return summary counts.

    Implements canonical run semantics using ``CASE_HASH`` for identity:

    * Each run must contain a ``CASE_HASH`` value extracted from
      ``env_case.xml``.  Runs missing ``CASE_HASH`` are rejected.
    * Case lookup/creation is done by ``case_hash`` — no fallback to
      directory name or other heuristics.
    * The first successful run per case becomes the canonical baseline
      (``run_config_deltas = None``).
    * Non-canonical simulations store a single dict of configuration
      differences versus the canonical.
    * Duplicate detection is based on ``execution_id`` uniqueness.

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
        Dataclass containing list of SimulationCreate objects, counts of
        created and duplicate simulations, and any errors encountered.
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

    simulations: list[SimulationCreate] = []
    duplicate_count = 0
    skipped_count = 0
    errors: list[dict[str, str]] = []

    # Track canonical metadata per case_hash for batch processing.
    # Handles the case where multiple runs for the same (new) case
    # appear in a single archive before any are persisted.
    canonical_cache: dict[str, SimulationMetadata] = {}

    for exp_dir, metadata in all_simulations.items():
        execution_id = _derive_execution_id(exp_dir)

        try:
            # Validate CASE_HASH presence — mandatory for case identity.
            case_hash = metadata.get("case_hash")
            if not case_hash:
                raise ValueError(
                    f"CASE_HASH is required but missing from '{exp_dir}'. "
                    "Ensure env_case.xml contains a CASE_HASH entry."
                )

            case_name = metadata.get("case_name") or "unknown"
            machine_id = _resolve_machine_id(metadata, db)

            # Get or create Case by case_hash (not by name).
            case = _get_or_create_case(db, case_hash=case_hash, name=case_name)

            # Duplicate check by execution_id.
            existing_sim = _find_existing_simulation(db, execution_id)
            if existing_sim:
                logger.info(
                    f"Simulation with execution_id='{execution_id}' "
                    f"already exists. Skipping duplicate from {exp_dir}."
                )
                duplicate_count += 1

                # Seed canonical cache if we haven't seen this case yet.
                if case_hash not in canonical_cache:
                    canonical_cache[case_hash] = metadata
                continue

            # Determine canonical metadata for this case.
            canonical_metadata: SimulationMetadata | None = None

            if case.canonical_simulation_id is not None:
                # Case already has a persisted canonical.
                canonical_sim = (
                    db.query(Simulation)
                    .filter(Simulation.id == case.canonical_simulation_id)
                    .first()
                )
                if canonical_sim:
                    canonical_metadata = _sim_to_metadata(canonical_sim)
            elif case_hash in canonical_cache:
                # Canonical assigned earlier in this batch (not yet persisted).
                canonical_metadata = canonical_cache[case_hash]

            if canonical_metadata is None:
                # First successful run → canonical baseline.
                canonical_cache[case_hash] = metadata

                sim_create = _map_metadata_to_schema(
                    metadata, db, machine_id, case.id, execution_id
                )
                simulations.append(sim_create)
                logger.info(
                    f"Mapped canonical simulation from {exp_dir}: "
                    f"{case_name} (hash={case_hash})"
                )
            else:
                # Subsequent successful run → separate Simulation with delta.
                delta = _compute_config_delta(canonical_metadata, metadata)
                run_config_deltas = delta if delta else None

                sim_create = _map_metadata_to_schema(
                    metadata,
                    db,
                    machine_id,
                    case.id,
                    execution_id,
                    run_config_deltas=run_config_deltas,
                )
                simulations.append(sim_create)
                if delta:
                    logger.info(
                        f"Non-canonical run in '{exp_dir}' has config "
                        f"differences from canonical: {list(delta.keys())}"
                    )
                else:
                    logger.info(
                        f"Non-canonical run in '{exp_dir}' has identical "
                        f"configuration to canonical."
                    )

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


def _derive_execution_id(exp_dir: str) -> str:
    """Extract execution_id from the experiment directory path.

    The execution_id is the basename of the experiment directory
    (e.g. ``1125772.260116-181605``).  Absolute filesystem paths are
    never stored.

    Raises
    ------
    ValueError
        If the derived execution_id is empty.
    """
    execution_id = os.path.basename(exp_dir)
    if not execution_id:
        raise ValueError(
            f"Cannot derive execution_id from experiment directory: '{exp_dir}'"
        )

    return execution_id


def _get_or_create_case(db: Session, case_hash: str, name: str) -> Case:
    """Get or create a Case record by case_hash.

    Parameters
    ----------
    db : Session
        Active database session.
    case_hash : str
        The CASE_HASH value from env_case.xml, used as the canonical
        identity for case grouping.
    name : str
        Human-readable case name (used when creating a new Case).
    """
    case = db.query(Case).filter(Case.case_hash == case_hash).first()

    if not case:
        case = Case(name=name, case_hash=case_hash)
        db.add(case)
        db.flush()
        logger.info(f"Created new Case: {name} (hash={case_hash})")

    return case


def _sim_to_metadata(sim: Simulation) -> SimulationMetadata:
    """Build a parser-style metadata dict from a persisted Simulation."""
    return {
        "case_name": sim.case.name if sim.case else None,
        "compset": sim.compset,
        "compset_alias": sim.compset_alias,
        "grid_name": sim.grid_name,
        "grid_resolution": sim.grid_resolution,
        "initialization_type": sim.initialization_type,
        "compiler": sim.compiler,
        "git_tag": sim.git_tag,
        "git_commit_hash": sim.git_commit_hash,
        "git_branch": sim.git_branch,
        "git_repository_url": sim.git_repository_url,
        "campaign": sim.campaign,
        "experiment_type": sim.experiment_type,
        "group_name": sim.group_name,
    }


def _compute_config_delta(
    canonical: SimulationMetadata,
    other: SimulationMetadata,
) -> dict[str, dict[str, str | None]]:
    """Compare two run metadata dicts and return configuration differences.

    Only the fields in :data:`_CONFIG_DELTA_FIELDS` are compared.

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


def _resolve_machine_id(metadata: SimulationMetadata, db: Session) -> UUID:
    """Resolve machine name to machine ID from the database.

    Raises
    ------
    ValueError
        If machine name is missing from metadata.
    LookupError
        If machine name cannot be found in database.
    """
    machine_name = metadata.get("machine")
    if not machine_name:
        raise ValueError("Machine name is required but not found in metadata")

    machine = db.query(Machine).filter(Machine.name == machine_name).first()
    if not machine:
        raise LookupError(
            f"Machine '{machine_name}' not found in database. "
            "Please ensure the machine exists before uploading."
        )
    return machine.id


def _find_existing_simulation(db: Session, execution_id: str) -> Simulation | None:
    """Find existing simulation by execution_id."""
    return db.query(Simulation).filter(Simulation.execution_id == execution_id).first()


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
    metadata: SimulationMetadata,
    db: Session,
    machine_id: UUID,
    case_id: UUID,
    execution_id: str,
    run_config_deltas: dict[str, dict[str, str | None]] | None = None,
) -> SimulationCreate:
    """Map parser metadata to SimulationCreate schema with type conversions.

    Parameters
    ----------
    metadata : SimulationMetadata
        Dictionary of parsed simulation metadata with string values.
    db : Session
        SQLAlchemy database session (used for validation context).
    machine_id : UUID
        Pre-extracted machine ID.
    case_id : UUID
        ID of the Case this simulation belongs to.
    execution_id : str
        Unique execution identifier derived from the archive directory.
    run_config_deltas : dict | None
        Configuration differences vs canonical baseline, or None.

    Returns
    -------
    SimulationCreate
        Schema object ready for database insertion.
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
            "caseId": case_id,
            "executionId": execution_id,
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
            # Canonical run semantics
            "runConfigDeltas": run_config_deltas,
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
