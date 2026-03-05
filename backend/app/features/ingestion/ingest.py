"""
Module for ingesting simulation archives and mapping to DB schemas.

Canonical run semantics for performance_archive ingestion:
  - A run is "successful" only if all required metadata files are present.
  - case_name (from timing files) is the identity for Case grouping.
  - The first successful run per case is the canonical baseline.
  - Each run creates a Simulation linked to a Case via case_id.
  - Canonical simulation has run_config_deltas = None.
  - Non-canonical runs store config differences vs canonical.
  - Incomplete runs are skipped at the parser level.
  - Re-processing is idempotent due to execution_id uniqueness.

Caching for canonical lookup:
  - canonical_cache: canonical metadata for new cases in this ingest batch,
    keyed by case_name.
  - persisted_canonical_cache: canonical metadata for cases already in DB,
    keyed by case.id, to avoid repeated DB queries.
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
        "execution_type",
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


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
) -> IngestArchiveResult:
    """Ingest a simulation archive and return summary counts.

    Implements canonical run semantics:

    - Case lookup/creation is done by ``case_name`` from timing files.
    - The first successful run per case becomes the canonical baseline
      (``run_config_deltas = None``).
    - Non-canonical simulations store a single dict of configuration
      differences versus the canonical.
    - Duplicate detection is based on ``execution_id`` uniqueness.
    - Uses two caches to avoid redundant work:
       - ``canonical_cache``: Tracks the canonical simulation metadata for each
           new case found in the current ingest batch (keyed by case_name). This
           ensures that if multiple new runs for the same case appear in a
           single archive, all are compared against the same in-batch canonical
           baseline.
       - ``persisted_canonical_cache``: Tracks canonical simulation metadata
           for cases already in the database (keyed by case.id). This avoids
           repeated database queries for the canonical simulation of a case
           when processing multiple runs for the same case in a single ingest
           operation.

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

    all_simulations, skipped_count = main_parser(
        archive_path_resolved, output_dir_resolved
    )

    if not all_simulations:
        logger.warning(f"No simulations found in archive: {archive_path_resolved}")

        return IngestArchiveResult(
            simulations=[],
            created_count=0,
            duplicate_count=0,
            skipped_count=skipped_count,
        )

    simulations: list[SimulationCreate] = []
    duplicate_count = 0
    errors: list[dict[str, str]] = []
    canonical_cache: dict[str, SimulationMetadata] = {}
    persisted_canonical_cache: dict[UUID, SimulationMetadata | None] = {}

    for execution_dir, metadata in all_simulations.items():
        try:
            simulation, is_duplicate = _process_simulation_for_ingest(
                execution_dir=execution_dir,
                metadata=metadata,
                db=db,
                canonical_cache=canonical_cache,
                persisted_canonical_cache=persisted_canonical_cache,
            )

            if is_duplicate:
                duplicate_count += 1
                continue

            if simulation is not None:
                simulations.append(simulation)

        except (ValueError, LookupError, ValidationError) as e:
            logger.error(f"Failed to process simulation from {execution_dir}: {e}")

            errors.append(
                {
                    "execution_dir": str(execution_dir),
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


def _process_simulation_for_ingest(
    execution_dir: str,
    metadata: SimulationMetadata,
    db: Session,
    canonical_cache: dict[str, SimulationMetadata],
    persisted_canonical_cache: dict[UUID, SimulationMetadata | None],
) -> tuple[SimulationCreate | None, bool]:
    """Process one parsed simulation entry.

    Parameters
    ----------
    execution_dir : str
        Execution directory name (used to derive execution_id).
    metadata : SimulationMetadata
        Parsed metadata dictionary for the simulation.
    db : Session
        Active database session for lookups and case resolution.
    canonical_cache : dict[str, SimulationMetadata]
        In-memory cache of canonical metadata per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationMetadata | None]
        Cache of canonical metadata loaded from the database by case_id.

    Returns
    -------
    tuple[SimulationCreate | None, bool]
        ``(simulation, is_duplicate)`` where ``simulation`` is populated
        only for new records and ``is_duplicate`` is True when an existing
        ``execution_id`` was found.
    """
    execution_id = _derive_execution_id(execution_dir)
    case_name = _require_case_name(metadata, execution_dir)
    machine_id = _resolve_machine_id(metadata, db)
    case = _resolve_case(metadata, case_name, db)

    if _is_duplicate_simulation(execution_id, execution_dir, db):
        _seed_canonical_cache_from_duplicate(case_name, metadata, canonical_cache)
        return None, True

    simulation = _build_simulation_create(
        execution_dir=execution_dir,
        metadata=metadata,
        execution_id=execution_id,
        machine_id=machine_id,
        case=case,
        canonical_cache=canonical_cache,
        persisted_canonical_cache=persisted_canonical_cache,
        db=db,
    )

    return simulation, False


def _require_case_name(metadata: SimulationMetadata, execution_dir: str) -> str:
    """Return case_name from metadata or raise a descriptive error."""
    case_name = metadata.get("case_name")

    if not case_name:
        raise ValueError(
            f"case_name is required but missing from '{execution_dir}'. "
            "Cannot determine Case identity."
        )

    return case_name


def _resolve_case(metadata: SimulationMetadata, case_name: str, db: Session) -> Case:
    """Resolve or create the Case for the current metadata row."""
    case_group = metadata.get("case_group")

    result = _get_or_create_case(db, name=case_name, case_group=case_group)

    return result


def _is_duplicate_simulation(
    execution_id: str, execution_dir: str, db: Session
) -> bool:
    """Return True when a simulation with execution_id already exists."""
    existing_sim = _find_existing_simulation(db, execution_id)

    if not existing_sim:
        return False

    logger.info(
        f"Simulation with execution_id='{execution_id}' "
        f"already exists. Skipping duplicate from {execution_dir}."
    )
    return True


def _seed_canonical_cache_from_duplicate(
    case_name: str,
    metadata: SimulationMetadata,
    canonical_cache: dict[str, SimulationMetadata],
) -> None:
    """Seed per-case canonical cache using duplicate metadata when needed."""
    if case_name not in canonical_cache:
        canonical_cache[case_name] = metadata


def _build_simulation_create(
    execution_dir: str,
    metadata: SimulationMetadata,
    execution_id: str,
    machine_id: UUID,
    case: Case,
    canonical_cache: dict[str, SimulationMetadata],
    persisted_canonical_cache: dict[UUID, SimulationMetadata | None],
    db: Session,
) -> SimulationCreate:
    """Create a SimulationCreate using canonical baseline semantics.

    Parameters
    ----------
    execution_dir : str
        Execution directory name (used for logging context).
    metadata : SimulationMetadata
        Parsed metadata dictionary for the simulation.
    execution_id : str
        Unique execution identifier derived from the execution directory.
    machine_id : UUID
        Resolved machine ID from the database.
    case : Case
        Resolved Case object for this simulation.
    canonical_cache : dict[str, SimulationMetadata]
        In-memory cache of canonical metadata per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationMetadata | None]
        Cache of canonical metadata loaded from the database by case_id.
    db : Session
        Active database session for lookups and case resolution.
    """
    case_name = case.name
    canonical_metadata = _get_canonical_metadata_for_case(
        case=case,
        case_name=case_name,
        canonical_cache=canonical_cache,
        persisted_canonical_cache=persisted_canonical_cache,
        db=db,
    )

    if canonical_metadata is None:
        canonical_cache[case_name] = metadata

        simulation = _map_metadata_to_schema(
            metadata, machine_id, case.id, execution_id
        )
        logger.info(f"Mapped canonical simulation from {execution_dir}: {case_name}")

        return simulation

    delta = _compute_config_delta(canonical_metadata, metadata)
    run_config_deltas = delta if delta else None

    simulation = _map_metadata_to_schema(
        metadata, machine_id, case.id, execution_id, run_config_deltas=run_config_deltas
    )

    if delta:
        logger.info(
            f"Non-canonical run in '{execution_dir}' has config differences from "
            f"canonical: {list(delta.keys())}"
        )
    else:
        logger.info(
            f"Non-canonical run in '{execution_dir}' has identical configuration to canonical."
        )

    return simulation


def _get_canonical_metadata_for_case(
    case: Case,
    case_name: str,
    canonical_cache: dict[str, SimulationMetadata],
    persisted_canonical_cache: dict[UUID, SimulationMetadata | None],
    db: Session,
) -> SimulationMetadata | None:
    """Resolve canonical metadata from persisted canonical or batch cache.

    This function is useful for ensuring that all simulations of the same case
    within a batch are compared against a consistent canonical baseline.

    Parameters
    ----------
    case : Case
        The Case object for which to retrieve canonical metadata.
    case_name : str
        The name of the case, used for in-memory cache lookup.
    canonical_cache : dict[str, SimulationMetadata]
        In-memory cache of canonical metadata per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationMetadata | None]
        Cache of canonical metadata loaded from the database by case_id.

    Returns
    -------
    SimulationMetadata | None
        The canonical metadata for the case, or None if no canonical run exists.
    """
    if case.canonical_simulation_id is not None:
        if case.id in persisted_canonical_cache:
            return persisted_canonical_cache[case.id]

        canonical_sim = (
            db.query(Simulation)
            .filter(Simulation.id == case.canonical_simulation_id)
            .first()
        )

        if canonical_sim:
            canonical_metadata = _sim_to_metadata(canonical_sim)
            persisted_canonical_cache[case.id] = canonical_metadata

            return canonical_metadata

        persisted_canonical_cache[case.id] = None
        return None

    return canonical_cache.get(case_name)


def _derive_execution_id(execution_dir: str) -> str:
    """Extract execution_id from the execution directory path.

    The execution_id is the basename of the execution directory
    (e.g. ``1125772.260116-181605``).  Absolute filesystem paths are
    never stored.

    Parameters
    ----------
    execution_dir : str
        Execution directory name from the parser output (e.g. from timing files).

    Raises
    ------
    ValueError
        If the derived execution_id is empty.
    """
    execution_id = os.path.basename(execution_dir)
    if not execution_id:
        raise ValueError(
            f"Cannot derive execution_id from execution directory: '{execution_dir}'"
        )

    return execution_id


def _get_or_create_case(db: Session, name: str, case_group: str | None = None) -> Case:
    """Get or create a Case record by case name.

    Parameters
    ----------
    db : Session
        Active database session.
    name : str
        Case name derived from the execution (e.g. from timing files).
        Used as the canonical identity for case grouping.
    case_group : str | None
        Optional CASE_GROUP from env_case.xml.  Stored on ``Case``
        if present.  An existing non-null value is never overwritten
        with null; a conflicting non-null value logs a warning and
        keeps the original.

    Returns
    -------
    Case
        The existing or newly created Case object.
    """
    case = db.query(Case).filter(Case.name == name).first()

    if not case:
        case = Case(name=name, case_group=case_group)
        db.add(case)
        db.flush()
        logger.info(f"Created new Case: {name}")
    elif case_group is not None:
        if case.case_group is None:
            case.case_group = case_group
            db.flush()
        elif case.case_group != case_group:
            logger.warning(
                f"Conflicting CASE_GROUP for case '{name}': "
                f"existing='{case.case_group}', "
                f"new='{case_group}'. Retaining existing value."
            )

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
    }


def _compute_config_delta(
    canonical: SimulationMetadata,
    other: SimulationMetadata,
) -> dict[str, dict[str, str | None]]:
    """Compare two run metadata dicts and return configuration differences.

    Only the fields in :data:`_CONFIG_DELTA_FIELDS` are compared.

    Parameters
    ----------
    canonical : SimulationMetadata
        The canonical run metadata to compare against.
    other : SimulationMetadata
        The other run metadata to compare.

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

    Parameters
    ----------
    metadata : SimulationMetadata
        Parsed metadata dictionary for the simulation, expected to contain a
        "machine" key with the machine name.
    db : Session
        Active database session for querying the Machine table.

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
    """Find existing simulation by execution_id.

    Parameters
    ----------
    db : Session
        Active database session for querying the Simulation table.
    execution_id : str
        Unique execution identifier derived from the execution directory.

    Returns
    -------
    Simulation | None
        The existing Simulation object with the given execution_id, or None if
        not found.
    """
    result = (
        db.query(Simulation).filter(Simulation.execution_id == execution_id).first()
    )

    return result


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
            "experimentType": metadata.get("experiment_type"),
            "campaign": metadata.get("campaign"),
            "runStartDate": run_start_date,
            "runEndDate": run_end_date,
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
