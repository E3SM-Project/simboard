"""Module for ingesting simulation archives and mapping to DB schemas."""

import shlex
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from dateutil import parser as dateutil_parser
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.common.utils import _normalize_hpc_username
from app.core.logger import _setup_custom_logger
from app.features.catalog.enums import ArtifactKind, ExecutionStatus, SimulationType
from app.features.catalog.models import Case, Execution
from app.features.catalog.schemas import ArtifactCreate, ExecutionCreate
from app.features.ingestion.parsers.parser import main_parser
from app.features.ingestion.parsers.types import ParsedExecution
from app.features.machine.utils import parse_machine_name, resolve_machine_by_name

logger = _setup_custom_logger(__name__)

_STRING_ADAPTER = TypeAdapter(str)
_DATE_ADAPTER = TypeAdapter(date)
_DATETIME_ADAPTER = TypeAdapter(datetime)
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
CaseIdentity = tuple[str, UUID, str]


@dataclass
class IngestArchiveResult:
    """
    Structured result of an archive ingestion operation.

    Attributes
    ----------
    executions : list[ExecutionCreate]
        Collection of execution schema objects successfully parsed and
        validated from the archive.
    created_count : int
        Number of new executions eligible for creation.
    duplicate_count : int
        Number of executions skipped due to existing records in the database.
    skipped_count : int
        Number of incomplete runs that were skipped at the parser level.
    errors : list[dict[str, str]]
        List of ingestion errors encountered during processing.
    """

    executions: list[ExecutionCreate]
    created_count: int
    duplicate_count: int
    skipped_count: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionCreateDraft:
    """Normalized internal payload validated into ``ExecutionCreate``."""

    case_id: UUID | None
    execution_id: str
    compset: str | None
    compset_alias: str | None
    grid_name: str | None
    grid_resolution: str | None
    simulation_type: SimulationType
    status: ExecutionStatus
    campaign: str | None
    experiment_type: str | None
    initialization_type: str | None
    simulation_start_date: date | None
    simulation_end_date: date | None
    run_start_date: datetime | None
    run_end_date: datetime | None
    compiler: str | None
    git_repository_url: str | None
    git_branch: str | None
    git_tag: str | None
    git_commit_hash: str | None
    created_by: UUID | None
    last_updated_by: UUID | None
    case_hash: str | None = None
    compute_type: Literal["cpu", "gpu"] | None = None


def ingest_archive(
    archive_path: Path | str,
    output_dir: Path | str,
    db: Session,
    *,
    strict_validation: bool = False,
    hpc_username: str | None = None,
) -> IngestArchiveResult:
    """Ingest a simulation archive and return summary counts.

    - Case lookup/creation is done by ``case_name`` + machine + HPC username.
    - Duplicate detection is based on ``(case_id, execution_id)`` uniqueness.
    - CASE_HASH is preserved as per-execution metadata for grouping.

    Parameters
    ----------
    archive_path : Path | str
        Path to the archive file to ingest (.zip or .tar.gz).
    output_dir : Path | str
        Directory where extracted files will be stored.
    db : Session
        SQLAlchemy database session for machine and execution lookups.
    Returns
    -------
    IngestArchiveResult
        Dataclass containing list of ExecutionCreate objects, counts of
        created and duplicate executions, and any errors encountered.
    """
    archive_path_resolved = (
        Path(archive_path) if isinstance(archive_path, str) else archive_path
    )
    output_dir_resolved = (
        Path(output_dir) if isinstance(output_dir, str) else output_dir
    )

    parsed_executions, skipped_count = main_parser(
        archive_path_resolved,
        output_dir_resolved,
        strict_validation=strict_validation,
    )

    if not parsed_executions:
        logger.warning(f"No executions found in archive: {archive_path_resolved}")

        return IngestArchiveResult(
            executions=[],
            created_count=0,
            duplicate_count=0,
            skipped_count=skipped_count,
        )

    executions: list[ExecutionCreate] = []
    duplicate_count = 0
    errors: list[dict[str, str]] = []
    case_hash_cache: dict[CaseIdentity, str] = {}
    persisted_case_hash_cache: dict[UUID, str | None] = {}

    for parsed_execution in parsed_executions:
        try:
            execution, is_duplicate = _process_execution_for_ingest(
                parsed_execution=parsed_execution,
                db=db,
                case_hash_cache=case_hash_cache,
                persisted_case_hash_cache=persisted_case_hash_cache,
                request_hpc_username=hpc_username,
            )

            if is_duplicate:
                duplicate_count += 1
                continue

            if execution is not None:
                executions.append(execution)

        except (ValueError, LookupError, ValidationError) as e:
            logger.error(
                "Failed to process execution from %s: %s",
                parsed_execution.execution_dir,
                e,
            )

            errors.append(
                {
                    "execution_dir": parsed_execution.execution_dir,
                    "error_type": type(e).__name__,
                    "error": str(e),
                }
            )
            continue

    result = IngestArchiveResult(
        executions=executions,
        created_count=len(executions),
        duplicate_count=duplicate_count,
        skipped_count=skipped_count,
        errors=errors,
    )

    return result


def _process_execution_for_ingest(
    parsed_execution: ParsedExecution,
    db: Session,
    case_hash_cache: dict[CaseIdentity, str],
    persisted_case_hash_cache: dict[UUID, str | None],
    request_hpc_username: str | None = None,
) -> tuple[ExecutionCreate | None, bool]:
    """Process one parsed execution entry.

    Parameters
    ----------
    parsed_execution : ParsedExecution
        Parsed archive-derived metadata for the execution.
    db : Session
        Active database session for lookups and case resolution.
    Returns
    -------
    tuple[ExecutionCreate | None, bool]
        ``(execution, is_duplicate)`` where ``execution`` is populated
        only for new records and ``is_duplicate`` is True when an existing
        ``(case_id, execution_id)`` pair was found.
    """
    execution_id = parsed_execution.execution_id
    case_name = _require_case_name(parsed_execution)
    machine_id = _resolve_machine_id(parsed_execution, db)
    resolved_hpc_username = _resolve_case_hpc_username(
        parsed_execution,
        request_hpc_username,
    )

    existing_case = _find_case(
        db,
        name=case_name,
        machine_id=machine_id,
        hpc_username=resolved_hpc_username,
    )
    if existing_case is not None and _is_duplicate_execution(
        case=existing_case,
        execution_id=execution_id,
        execution_dir=parsed_execution.execution_dir,
        db=db,
    ):
        return None, True

    prevalidated_draft = _prevalidate_execution_create(
        parsed_execution,
    )
    case = existing_case or _resolve_case(
        parsed_execution,
        case_name,
        machine_id,
        resolved_hpc_username,
        db,
    )
    _track_case_hash_grouping(
        parsed_execution=parsed_execution,
        case=case,
        case_hash_cache=case_hash_cache,
        persisted_case_hash_cache=persisted_case_hash_cache,
        db=db,
    )
    execution = _build_execution_create(
        parsed_execution=parsed_execution,
        prevalidated_draft=prevalidated_draft,
        case=case,
    )

    return execution, False


def _track_case_hash_grouping(
    parsed_execution: ParsedExecution,
    case: Case,
    case_hash_cache: dict[CaseIdentity, str],
    persisted_case_hash_cache: dict[UUID, str | None],
    db: Session,
) -> None:
    """Track CASE_HASH values as within-case execution grouping metadata."""
    current_hash = parsed_execution.case_hash
    if not current_hash:
        return

    known_hash = _get_known_case_hash(
        case=case,
        case_hash_cache=case_hash_cache,
        persisted_case_hash_cache=persisted_case_hash_cache,
        db=db,
    )
    if known_hash is None:
        case_hash_cache.setdefault(_case_identity_key(case), current_hash)
        return

    case_hash_cache.setdefault(_case_identity_key(case), known_hash)
    if known_hash == current_hash:
        return

    logger.info(
        "Observed additional CASE_HASH for case '%s': known='%s', current='%s' "
        "from %s. Preserving per-execution hashes for grouping.",
        case.name,
        known_hash,
        current_hash,
        parsed_execution.execution_dir,
    )


def _get_known_case_hash(
    case: Case,
    case_hash_cache: dict[CaseIdentity, str],
    persisted_case_hash_cache: dict[UUID, str | None],
    db: Session,
) -> str | None:
    """Return first known CASE_HASH used for within-case execution grouping."""
    if case.id not in persisted_case_hash_cache:
        known_hash = (
            db.query(Execution.case_hash)
            .filter(
                Execution.case_id == case.id,
                Execution.case_hash.is_not(None),
            )
            .order_by(Execution.created_at.asc())
            .limit(1)
            .scalar()
        )
        persisted_case_hash_cache[case.id] = known_hash
        if known_hash is not None:
            case_hash_cache.setdefault(_case_identity_key(case), known_hash)

    known_hash = persisted_case_hash_cache[case.id]
    if known_hash is not None:
        return known_hash

    return case_hash_cache.get(_case_identity_key(case))


def _require_case_name(parsed_execution: ParsedExecution) -> str:
    """Return case_name from metadata or raise a descriptive error."""
    case_name = parsed_execution.case_name

    if not case_name:
        raise ValueError(
            f"case_name is required but missing from '{parsed_execution.execution_dir}'. "
            "Cannot determine Case identity."
        )

    return case_name


def _resolve_case(
    parsed_execution: ParsedExecution,
    case_name: str,
    machine_id: UUID,
    hpc_username: str,
    db: Session,
) -> Case:
    """Resolve or create the Case for the current metadata row."""
    case_group = parsed_execution.case_group

    result = _get_or_create_case(
        db,
        name=case_name,
        machine_id=machine_id,
        hpc_username=hpc_username,
        case_group=case_group,
    )

    return result


def _find_case(
    db: Session,
    name: str,
    machine_id: UUID,
    hpc_username: str,
) -> Case | None:
    """Return existing Case by normalized identity without creating one."""
    return (
        db.query(Case)
        .filter(
            Case.name == name,
            Case.machine_id == machine_id,
            Case.hpc_username == hpc_username,
        )
        .first()
    )


def _is_duplicate_execution(
    case: Case, execution_id: str, execution_dir: str, db: Session
) -> bool:
    """Return True when an execution with the same case/execution already exists."""
    existing_execution = _find_existing_execution(db, case.id, execution_id)

    if not existing_execution:
        return False

    logger.info(
        "Execution with case_name='%s' and execution_id='%s' already exists. "
        "Skipping duplicate from %s.",
        case.name,
        execution_id,
        execution_dir,
    )
    return True


def _build_execution_create(
    parsed_execution: ParsedExecution,
    prevalidated_draft: ExecutionCreateDraft,
    case: Case,
) -> ExecutionCreate:
    """Create an ExecutionCreate from parsed archive metadata."""
    execution = _validate_execution_create(replace(prevalidated_draft, case_id=case.id))
    execution = _attach_path_artifacts(execution, parsed_execution)
    logger.info(
        "Mapped execution from %s: %s", parsed_execution.execution_dir, case.name
    )
    return execution


def _attach_path_artifacts(
    execution: ExecutionCreate,
    parsed_execution: ParsedExecution,
) -> ExecutionCreate:
    path_artifacts = _build_path_artifacts(parsed_execution)
    if not path_artifacts:
        return execution

    return execution.model_copy(
        update={"artifacts": [*execution.artifacts, *path_artifacts]}
    )


def _build_path_artifacts(parsed_execution: ParsedExecution) -> list[ArtifactCreate]:
    path_artifacts: list[ArtifactCreate] = []

    output_path = _normalize_path_candidate(parsed_execution.output_path)
    archive_path = _normalize_path_candidate(parsed_execution.archive_path)
    run_script_path = _derive_case_run_script_path(parsed_execution.case_root)
    postprocessing_path = _extract_postprocessing_script_path(
        parsed_execution.postprocessing_script,
        execution_dir=parsed_execution.execution_dir,
    )

    _append_path_artifact(path_artifacts, ArtifactKind.OUTPUT, output_path)
    _append_path_artifact(path_artifacts, ArtifactKind.ARCHIVE, archive_path)
    _append_path_artifact(path_artifacts, ArtifactKind.RUN_SCRIPT, run_script_path)
    _append_path_artifact(
        path_artifacts,
        ArtifactKind.POSTPROCESS_SCRIPT,
        postprocessing_path,
    )

    return path_artifacts


def _append_path_artifact(
    artifacts: list[ArtifactCreate], kind: ArtifactKind, uri: str | None
) -> None:
    if uri is None:
        return

    artifacts.append(ArtifactCreate(kind=kind, uri=uri))


def _derive_case_run_script_path(case_root: str | None) -> str | None:
    normalized_case_root = _normalize_path_candidate(case_root)
    if normalized_case_root is None:
        return None

    return str(Path(normalized_case_root) / ".case.run")


def _extract_postprocessing_script_path(
    postprocessing_script: str | None,
    execution_dir: str,
) -> str | None:
    normalized_script = _normalize_path_candidate(postprocessing_script)
    if normalized_script is None:
        return None

    try:
        tokens = shlex.split(normalized_script)
    except ValueError:
        logger.warning(
            "Skipping POSTRUN_SCRIPT artifact for '%s': could not parse value '%s'.",
            execution_dir,
            normalized_script,
        )
        return None

    if not tokens:
        return None

    return tokens[0]


def _normalize_path_candidate(path_value: str | None) -> str | None:
    if path_value is None:
        return None

    normalized = path_value.strip()
    if not normalized:
        return None

    return normalized


def _prevalidate_execution_create(
    parsed_execution: ParsedExecution,
) -> ExecutionCreateDraft:
    """Build and validate non-identity execution fields before create."""
    draft = _build_execution_create_draft(
        parsed_execution=parsed_execution,
        case_id=None,
    )

    _validate_pre_case_draft(draft)

    return draft


def _validate_pre_case_draft(draft: ExecutionCreateDraft) -> None:
    """Validate the draft fields that must succeed before case creation."""
    for field_name in (
        "execution_id",
        "compset",
        "compset_alias",
        "grid_name",
        "grid_resolution",
        "initialization_type",
    ):
        _STRING_ADAPTER.validate_python(getattr(draft, field_name))

    _DATE_ADAPTER.validate_python(draft.simulation_start_date)

    if draft.git_repository_url is not None:
        _HTTP_URL_ADAPTER.validate_python(draft.git_repository_url)


def _get_or_create_case(
    db: Session,
    name: str,
    machine_id: UUID,
    hpc_username: str,
    case_group: str | None = None,
) -> Case:
    """Get or create a Case record by normalized identity.

    Parameters
    ----------
    db : Session
        Active database session.
    name : str
        Case name derived from the execution (e.g. from timing files).
    machine_id : UUID
        Resolved machine identifier for the execution.
    hpc_username : str
        Resolved HPC username for the execution.
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
    case = _find_case(
        db,
        name=name,
        machine_id=machine_id,
        hpc_username=hpc_username,
    )

    if not case:
        case = Case(
            name=name,
            machine_id=machine_id,
            hpc_username=hpc_username,
            case_group=case_group,
        )
        db.add(case)
        db.flush()
        logger.info("Created new Case: %s [%s, %s]", name, machine_id, hpc_username)
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


def _case_identity_key(case: Case) -> CaseIdentity:
    return (case.name, case.machine_id, case.hpc_username)


def _resolve_case_hpc_username(
    parsed_execution: ParsedExecution,
    request_hpc_username: str | None,
) -> str:
    resolved_hpc_username = _normalize_hpc_username(parsed_execution.hpc_username)
    if resolved_hpc_username is not None:
        return resolved_hpc_username

    request_hpc_username = _normalize_hpc_username(request_hpc_username)
    if request_hpc_username is not None:
        return request_hpc_username

    raise ValueError(
        f"hpc_username is required but missing from '{parsed_execution.execution_dir}'. "
        "Provide it in parsed metadata or request payload."
    )


def _resolve_machine_id(metadata: ParsedExecution, db: Session) -> UUID:
    """Resolve machine name to machine ID from the database.

    Parameters
    ----------
    metadata : ParsedExecution
        Parsed metadata for the execution, expected to contain a
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


def _find_existing_execution(
    db: Session, case_id: UUID, execution_id: str
) -> Execution | None:
    """Find an existing execution by case/execution pair.

    Parameters
    ----------
    db : Session
        Active database session for querying the Execution table.
    case_id : UUID
        Case identifier paired with the execution identifier.
    execution_id : str
        Execution identifier derived from the timing-file LID.

    Returns
    -------
    Execution | None
        The existing Execution object with the given case/execution pair,
        or None if not found.
    """
    result = (
        db.query(Execution)
        .filter(
            Execution.case_id == case_id,
            Execution.execution_id == execution_id,
        )
        .first()
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


def _build_execution_create_draft(
    parsed_execution: ParsedExecution,
    case_id: UUID | None,
) -> ExecutionCreateDraft:
    """Build a normalized internal draft for ``ExecutionCreate`` validation.

    Parameters
    ----------
    parsed_execution : ParsedExecution
        Parsed archive-derived metadata with string values.
    machine_id : UUID
        Pre-extracted machine ID.
    case_id : UUID
        ID of the Case this execution belongs to.
    Returns
    -------
    ExecutionCreateDraft
        Typed ingest draft ready for schema validation.
    """
    simulation_start_date = _parse_date_field(parsed_execution.simulation_start_date)
    simulation_end_date = _parse_date_field(parsed_execution.simulation_end_date)

    run_start_date = _parse_datetime_field(parsed_execution.run_start_date)
    run_end_date = _parse_datetime_field(parsed_execution.run_end_date)

    git_repository_url = _normalize_git_url(parsed_execution.git_repository_url)
    simulation_type = _normalize_simulation_type(None)
    status = _normalize_execution_status(parsed_execution.status)
    _, compute_type = parse_machine_name(parsed_execution.machine or "")

    execution_draft = ExecutionCreateDraft(
        case_id=case_id,
        execution_id=parsed_execution.execution_id,
        compset=parsed_execution.compset,
        compset_alias=parsed_execution.compset_alias,
        grid_name=parsed_execution.grid_name,
        grid_resolution=parsed_execution.grid_resolution,
        simulation_type=simulation_type,
        status=status,
        campaign=parsed_execution.campaign,
        experiment_type=parsed_execution.experiment_type,
        initialization_type=parsed_execution.initialization_type,
        simulation_start_date=simulation_start_date,
        simulation_end_date=simulation_end_date,
        run_start_date=run_start_date,
        run_end_date=run_end_date,
        compiler=parsed_execution.compiler,
        compute_type=compute_type,
        git_repository_url=git_repository_url,
        git_branch=parsed_execution.git_branch,
        git_tag=parsed_execution.git_tag,
        git_commit_hash=parsed_execution.git_commit_hash,
        created_by=None,
        last_updated_by=None,
        case_hash=parsed_execution.case_hash,
    )

    return execution_draft


def _validate_execution_create(draft: ExecutionCreateDraft) -> ExecutionCreate:
    """Validate a typed ingest draft into ``ExecutionCreate``."""
    return ExecutionCreate.model_validate(
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


def _normalize_execution_status(value: str | None) -> ExecutionStatus:
    """Return a valid ExecutionStatus enum value with CREATED fallback."""
    if not value:
        return ExecutionStatus.CREATED

    normalized = value.strip()
    if not normalized:
        return ExecutionStatus.CREATED

    try:
        return ExecutionStatus(normalized)
    except ValueError:
        try:
            return ExecutionStatus.__members__[normalized.upper()]
        except KeyError:
            logger.warning(
                "Unknown status '%s'; defaulting to '%s'.",
                value,
                ExecutionStatus.CREATED.value,
            )
            return ExecutionStatus.CREATED


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


def _parse_date_field(value: str | None) -> date | None:
    """Parse a calendar date, rejecting values not at midnight UTC."""
    if not value:
        return None
    try:
        parsed = dateutil_parser.parse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        if parsed.time() != time.min:
            raise ValueError("Model date datetime must represent midnight UTC")

        return parsed.date()
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse date '{value}': {e}")

        return None
