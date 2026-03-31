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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dateutil import parser as dateutil_parser
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.parser import main_parser
from app.features.ingestion.parsers.types import ParsedSimulation
from app.features.machine.utils import resolve_machine_by_name
from app.features.simulation.config_delta import SimulationConfigSnapshot
from app.features.simulation.enums import SimulationStatus, SimulationType
from app.features.simulation.models import Case, Simulation
from app.features.simulation.schemas import SimulationCreate

logger = _setup_custom_logger(__name__)


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


@dataclass(frozen=True)
class SimulationCreateDraft:
    """Normalized internal payload validated into ``SimulationCreate``."""

    case_id: UUID
    execution_id: str
    compset: str | None
    compset_alias: str | None
    grid_name: str | None
    grid_resolution: str | None
    simulation_type: SimulationType
    status: SimulationStatus
    campaign: str | None
    experiment_type: str | None
    initialization_type: str | None
    machine_id: UUID
    simulation_start_date: datetime | None
    simulation_end_date: datetime | None
    run_start_date: datetime | None
    run_end_date: datetime | None
    compiler: str | None
    git_repository_url: str | None
    git_branch: str | None
    git_tag: str | None
    git_commit_hash: str | None
    created_by: UUID | None
    last_updated_by: UUID | None
    hpc_username: str | None
    run_config_deltas: dict[str, dict[str, str | None]] | None = None


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
    *,
    strict_validation: bool = False,
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

    parsed_simulations, skipped_count = main_parser(
        archive_path_resolved,
        output_dir_resolved,
        strict_validation=strict_validation,
    )

    if not parsed_simulations:
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
    canonical_cache: dict[str, SimulationConfigSnapshot] = {}
    persisted_canonical_cache: dict[UUID, SimulationConfigSnapshot | None] = {}

    for parsed_simulation in parsed_simulations:
        try:
            simulation, is_duplicate = _process_simulation_for_ingest(
                parsed_simulation=parsed_simulation,
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
            logger.error(
                "Failed to process simulation from %s: %s",
                parsed_simulation.execution_dir,
                e,
            )

            errors.append(
                {
                    "execution_dir": parsed_simulation.execution_dir,
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
    parsed_simulation: ParsedSimulation,
    db: Session,
    canonical_cache: dict[str, SimulationConfigSnapshot],
    persisted_canonical_cache: dict[UUID, SimulationConfigSnapshot | None],
) -> tuple[SimulationCreate | None, bool]:
    """Process one parsed simulation entry.

    Parameters
    ----------
    parsed_simulation : ParsedSimulation
        Parsed archive-derived metadata for the simulation.
    db : Session
        Active database session for lookups and case resolution.
    canonical_cache : dict[str, SimulationConfigSnapshot]
        In-memory cache of canonical config values per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationConfigSnapshot | None]
        Cache of canonical metadata loaded from the database by case_id.

    Returns
    -------
    tuple[SimulationCreate | None, bool]
        ``(simulation, is_duplicate)`` where ``simulation`` is populated
        only for new records and ``is_duplicate`` is True when an existing
        ``execution_id`` was found.
    """
    execution_id = parsed_simulation.execution_id
    case_name = _require_case_name(parsed_simulation)
    machine_id = _resolve_machine_id(parsed_simulation, db)
    case = _resolve_case(parsed_simulation, case_name, db)

    if _is_duplicate_simulation(execution_id, parsed_simulation.execution_dir, db):
        _seed_canonical_cache_from_duplicate(
            case_name, parsed_simulation, canonical_cache
        )
        return None, True

    simulation = _build_simulation_create(
        parsed_simulation=parsed_simulation,
        machine_id=machine_id,
        case=case,
        canonical_cache=canonical_cache,
        persisted_canonical_cache=persisted_canonical_cache,
        db=db,
    )

    return simulation, False


def _require_case_name(parsed_simulation: ParsedSimulation) -> str:
    """Return case_name from metadata or raise a descriptive error."""
    case_name = parsed_simulation.case_name

    if not case_name:
        raise ValueError(
            f"case_name is required but missing from '{parsed_simulation.execution_dir}'. "
            "Cannot determine Case identity."
        )

    return case_name


def _resolve_case(
    parsed_simulation: ParsedSimulation, case_name: str, db: Session
) -> Case:
    """Resolve or create the Case for the current metadata row."""
    case_group = parsed_simulation.case_group

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
    parsed_simulation: ParsedSimulation,
    canonical_cache: dict[str, SimulationConfigSnapshot],
) -> None:
    """Seed per-case canonical cache using duplicate metadata when needed."""
    if case_name not in canonical_cache:
        canonical_cache[case_name] = _build_config_snapshot(parsed_simulation)


def _build_simulation_create(
    parsed_simulation: ParsedSimulation,
    machine_id: UUID,
    case: Case,
    canonical_cache: dict[str, SimulationConfigSnapshot],
    persisted_canonical_cache: dict[UUID, SimulationConfigSnapshot | None],
    db: Session,
) -> SimulationCreate:
    """Create a SimulationCreate using canonical baseline semantics.

    Parameters
    ----------
    parsed_simulation : ParsedSimulation
        Parsed archive-derived metadata for the simulation.
    machine_id : UUID
        Resolved machine ID from the database.
    case : Case
        Resolved Case object for this simulation.
    canonical_cache : dict[str, SimulationConfigSnapshot]
        In-memory cache of canonical metadata per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationConfigSnapshot | None]
        Cache of canonical metadata loaded from the database by case_id.
    db : Session
        Active database session for lookups and case resolution.
    """
    case_name = case.name
    canonical_snapshot = _get_canonical_metadata_for_case(
        case=case,
        case_name=case_name,
        canonical_cache=canonical_cache,
        persisted_canonical_cache=persisted_canonical_cache,
        db=db,
    )

    if canonical_snapshot is None:
        canonical_cache[case_name] = _build_config_snapshot(parsed_simulation)

        simulation = _validate_simulation_create(
            _build_simulation_create_draft(
                parsed_simulation=parsed_simulation,
                machine_id=machine_id,
                case_id=case.id,
            )
        )
        logger.info(
            "Mapped canonical simulation from %s: %s",
            parsed_simulation.execution_dir,
            case_name,
        )

        return simulation

    delta = canonical_snapshot.diff(_build_config_snapshot(parsed_simulation))
    run_config_deltas = delta if delta else None
    simulation_draft = _build_simulation_create_draft(
        parsed_simulation=parsed_simulation,
        machine_id=machine_id,
        case_id=case.id,
        run_config_deltas=run_config_deltas,
    )
    simulation = _validate_simulation_create(simulation_draft)

    if delta:
        logger.info(
            "Non-canonical run in '%s' has config differences from canonical: %s",
            parsed_simulation.execution_dir,
            list(delta.keys()),
        )
    else:
        logger.info(
            "Non-canonical run in '%s' has identical configuration to canonical.",
            parsed_simulation.execution_dir,
        )

    return simulation


def _get_canonical_metadata_for_case(
    case: Case,
    case_name: str,
    canonical_cache: dict[str, SimulationConfigSnapshot],
    persisted_canonical_cache: dict[UUID, SimulationConfigSnapshot | None],
    db: Session,
) -> SimulationConfigSnapshot | None:
    """Resolve canonical metadata from persisted canonical or batch cache.

    This function is useful for ensuring that all simulations of the same case
    within a batch are compared against a consistent canonical baseline.

    Parameters
    ----------
    case : Case
        The Case object for which to retrieve canonical metadata.
    case_name : str
        The name of the case, used for in-memory cache lookup.
    canonical_cache : dict[str, SimulationConfigSnapshot]
        In-memory cache of canonical metadata per case_name for the current batch.
    persisted_canonical_cache : dict[UUID, SimulationConfigSnapshot | None]
        Cache of canonical metadata loaded from the database by case_id.

    Returns
    -------
    SimulationConfigSnapshot | None
        The canonical config snapshot for the case, or None if no canonical run exists.
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
            canonical_snapshot = _build_config_snapshot(canonical_sim)
            persisted_canonical_cache[case.id] = canonical_snapshot

            return canonical_snapshot

        persisted_canonical_cache[case.id] = None
        return None

    return canonical_cache.get(case_name)


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


def _build_config_snapshot(
    source: ParsedSimulation | Simulation,
) -> SimulationConfigSnapshot:
    """Return a normalized config snapshot for canonical delta comparison."""
    snapshot_values: dict[str, str | None] = {}

    for field_name in SimulationConfigSnapshot.field_names():
        if field_name == "simulation_type" and isinstance(source, ParsedSimulation):
            snapshot_values[field_name] = SimulationType.UNKNOWN.value
            continue

        value = getattr(source, field_name)

        if isinstance(source, ParsedSimulation):
            normalized_value = value
        else:
            normalized_value = _stringify_config_value(value)

        if field_name == "git_repository_url":
            normalized_value = _normalize_git_url(normalized_value)

        snapshot_values[field_name] = normalized_value

    return SimulationConfigSnapshot(**snapshot_values)


def _stringify_config_value(value: object) -> str | None:
    """Convert enum-like config values to strings for delta comparison."""
    if value is None:
        return None

    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value

    if isinstance(value, str):
        return value

    return str(value)


def _resolve_machine_id(metadata: ParsedSimulation, db: Session) -> UUID:
    """Resolve machine name to machine ID from the database.

    Parameters
    ----------
    metadata : ParsedSimulation
        Parsed metadata for the simulation, expected to contain a
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
    machine_name = metadata.machine
    if not machine_name:
        raise ValueError("Machine name is required but not found in metadata")

    machine = resolve_machine_by_name(db, machine_name)
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
        Unique execution identifier derived from the timing-file LID.

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


def _build_simulation_create_draft(
    parsed_simulation: ParsedSimulation,
    machine_id: UUID,
    case_id: UUID,
    run_config_deltas: dict[str, dict[str, str | None]] | None = None,
) -> SimulationCreateDraft:
    """Build a normalized internal draft for ``SimulationCreate`` validation.

    Parameters
    ----------
    parsed_simulation : ParsedSimulation
        Parsed archive-derived metadata with string values.
    machine_id : UUID
        Pre-extracted machine ID.
    case_id : UUID
        ID of the Case this simulation belongs to.
    run_config_deltas : dict | None
        Configuration differences vs canonical baseline, or None.

    Returns
    -------
    SimulationCreateDraft
        Typed ingest draft ready for schema validation.
    """
    # Parse datetime fields using the shared utility function.
    simulation_start_date = _parse_datetime_field(
        parsed_simulation.simulation_start_date
    )
    simulation_end_date = _parse_datetime_field(parsed_simulation.simulation_end_date)

    run_start_date = _parse_datetime_field(parsed_simulation.run_start_date)
    run_end_date = _parse_datetime_field(parsed_simulation.run_end_date)

    git_repository_url = _normalize_git_url(parsed_simulation.git_repository_url)
    simulation_type = _normalize_simulation_type(None)
    status = _normalize_simulation_status(parsed_simulation.status)

    simulation_draft = SimulationCreateDraft(
        case_id=case_id,
        execution_id=parsed_simulation.execution_id,
        compset=parsed_simulation.compset,
        compset_alias=parsed_simulation.compset_alias,
        grid_name=parsed_simulation.grid_name,
        grid_resolution=parsed_simulation.grid_resolution,
        simulation_type=simulation_type,
        status=status,
        campaign=parsed_simulation.campaign,
        experiment_type=parsed_simulation.experiment_type,
        initialization_type=parsed_simulation.initialization_type,
        machine_id=machine_id,
        simulation_start_date=simulation_start_date,
        simulation_end_date=simulation_end_date,
        run_start_date=run_start_date,
        run_end_date=run_end_date,
        compiler=parsed_simulation.compiler,
        git_repository_url=git_repository_url,
        git_branch=parsed_simulation.git_branch,
        git_tag=parsed_simulation.git_tag,
        git_commit_hash=parsed_simulation.git_commit_hash,
        created_by=None,
        last_updated_by=None,
        hpc_username=parsed_simulation.hpc_username,
        run_config_deltas=run_config_deltas,
    )

    return simulation_draft


def _validate_simulation_create(draft: SimulationCreateDraft) -> SimulationCreate:
    """Validate a typed ingest draft into ``SimulationCreate``."""
    return SimulationCreate.model_validate(
        draft,
        by_name=True,
        from_attributes=True,
    )


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
