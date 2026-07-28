from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, asc, desc, distinct, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.assistant.orchestrator import is_summary_llm_available
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.machine.utils import resolve_machine_by_name
from app.features.simulation.enums import (
    ExecutionStatus,
    ExternalLinkKind,
    SimulationStatus,
    SimulationType,
)
from app.features.simulation.link_utils import merge_execution_and_case_links
from app.features.simulation.models import Artifact, Case, Execution, ExternalLink
from app.features.simulation.schemas import (
    CaseDetailOut,
    CaseFilterOptionsOut,
    CaseListItemOut,
    CasePageOut,
    CaseSummaryOut,
    CaseUpdate,
    CatalogOverviewOut,
    DiagnosticsLinkRequest,
    FilterOptionOut,
    SimulationCreate,
    SimulationFilterOptionsOut,
    SimulationListItemOut,
    SimulationOut,
    SimulationPageOut,
    SimulationSummaryCapabilitiesOut,
    SimulationSummaryOut,
    SimulationUpdate,
)
from app.features.user.manager import can_edit_managed_content, current_active_user
from app.features.user.models import User, UserRole

simulation_router = APIRouter(prefix="/simulations", tags=["Simulations"])
case_router = APIRouter(prefix="/cases", tags=["Cases"])
diagnostics_router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])


@case_router.get(
    "",
    response_model=CasePageOut,
    responses={
        200: {"description": "List all cases."},
        500: {"description": "Internal server error."},
    },
)
def list_cases(  # noqa: C901
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    name: str | None = Query(None),
    case_group: str | None = Query(None),
    machine_id: UUID | None = Query(None),
    hpc_username: str | None = Query(None),
    execution_id: str | None = Query(None),
    status_filter: SimulationStatus | None = Query(None, alias="status"),
    simulation_type: SimulationType | None = Query(None),
    campaign: str | None = Query(None),
    initialization_type: str | None = Query(None),
    compiler: str | None = Query(None),
    git_tag: str | None = Query(None),
    created_by: UUID | None = Query(None),
    sort_by: str = Query(
        "updated_at",
        pattern=(
            "^(updated_at|created_at|name|case_group|machine_name|hpc_username|"
            "simulation_count)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> CasePageOut:
    """Return one lightweight, server-filtered case page."""
    query = db.query(Case)
    if search:
        query = query.filter(Case.name.ilike(f"%{search.strip()}%"))
    if name:
        query = query.filter(Case.name == name)
    if case_group:
        query = query.filter(Case.case_group == case_group)
    if machine_id:
        query = query.filter(Case.machine_id == machine_id)
    if hpc_username:
        query = query.filter(Case.hpc_username == hpc_username)
    simulation_predicates: list[ColumnElement[bool]] = []
    if execution_id:
        simulation_predicates.append(
            Execution.execution_id.ilike(f"%{execution_id.strip()}%")
        )
    if status_filter:
        simulation_predicates.append(
            Execution.status == ExecutionStatus(status_filter.value)
        )
    if simulation_type:
        simulation_predicates.append(Execution.simulation_type == simulation_type)
    for column, value in (
        (Execution.campaign, campaign),
        (Execution.initialization_type, initialization_type),
        (Execution.compiler, compiler),
        (Execution.git_tag, git_tag),
        (Execution.created_by, created_by),
    ):
        if value is not None:
            simulation_predicates.append(column == value)
    if simulation_predicates:
        query = query.filter(Case.executions.any(and_(*simulation_predicates)))

    total = query.order_by(None).count()
    simulation_count = (
        db.query(func.count(Execution.id))
        .filter(Execution.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
    )
    rows_query = query.join(Case.machine).with_entities(
        Case.id,
        Case.name,
        Case.case_group,
        Case.machine_id,
        Machine.name.label("machine_name"),
        Case.hpc_username,
        simulation_count.label("simulation_count"),
        Case.created_at,
        Case.updated_at,
    )
    sort_column = {
        "updated_at": Case.updated_at,
        "created_at": Case.created_at,
        "name": Case.name,
        "case_group": Case.case_group,
        "machine_name": Machine.name,
        "hpc_username": Case.hpc_username,
        "simulation_count": simulation_count,
    }[sort_by]
    ordering = asc(sort_column) if sort_order == "asc" else desc(sort_column)
    rows = (
        rows_query.order_by(ordering, Case.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CasePageOut(
        items=[CaseListItemOut(**row._asdict()) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@case_router.get("/overview", response_model=CatalogOverviewOut)
def get_catalog_overview(
    db: Session = Depends(get_database_session),
) -> CatalogOverviewOut:
    """Return fixed-size aggregate data used by homepage."""
    total_cases = db.query(func.count(Case.id)).scalar() or 0
    total_simulations = db.query(func.count(Execution.id)).scalar() or 0
    latest_submission = db.query(func.max(Execution.created_at)).scalar()
    machine_count_rows = (
        db.query(Case.machine_id, func.count(Case.id)).group_by(Case.machine_id).all()
    )
    machine_counts: dict[UUID, int] = {
        machine_id: count for machine_id, count in machine_count_rows
    }
    simulation_count = (
        db.query(func.count(Execution.id))
        .filter(Execution.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
    )
    latest_simulation_activity = (
        db.query(func.max(func.greatest(Execution.created_at, Execution.updated_at)))
        .filter(Execution.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
    )
    latest_activity = func.greatest(
        Case.updated_at,
        func.coalesce(latest_simulation_activity, Case.updated_at),
    )
    rows = (
        db.query(
            Case.id,
            Case.name,
            Case.case_group,
            Case.machine_id,
            Machine.name.label("machine_name"),
            Case.hpc_username,
            simulation_count.label("simulation_count"),
            Case.created_at,
            latest_activity.label("updated_at"),
        )
        .join(Machine, Machine.id == Case.machine_id)
        .order_by(latest_activity.desc(), Case.id.asc())
        .limit(6)
        .all()
    )
    return CatalogOverviewOut(
        total_cases=total_cases,
        total_simulations=total_simulations,
        latest_submission=latest_submission,
        machine_counts=machine_counts,
        recent_cases=[CaseListItemOut(**row._asdict()) for row in rows],
    )


@case_router.get("/filter-options", response_model=CaseFilterOptionsOut)
def get_case_filter_options(
    db: Session = Depends(get_database_session),
) -> CaseFilterOptionsOut:
    """Return distinct scalar case filter values."""
    return CaseFilterOptionsOut(
        names=_distinct_values(db, Case.name),
        case_groups=_distinct_values(db, Case.case_group),
        hpc_usernames=_distinct_values(db, Case.hpc_username),
        machine_ids=_distinct_values(db, Case.machine_id),
        machines=_machine_filter_options(db),
        statuses=_distinct_values(db, Execution.status),
        simulation_types=_distinct_values(db, Execution.simulation_type),
        campaigns=_distinct_values(db, Execution.campaign),
        initialization_types=_distinct_values(db, Execution.initialization_type),
        compilers=_distinct_values(db, Execution.compiler),
        git_tags=_distinct_values(db, Execution.git_tag),
        created_by_ids=_distinct_values(db, Execution.created_by),
        creators=_creator_filter_options(db),
    )


@case_router.get(
    "/names",
    response_model=list[str],
    responses={
        200: {"description": "List all case names."},
        500: {"description": "Internal server error."},
    },
)
def list_case_names(db: Session = Depends(get_database_session)) -> list[str]:
    """Return a sorted list of all case names.

    This lightweight endpoint avoids loading nested simulation data,
    making it suitable for populating filter dropdowns.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default provided by
        `Depends(get_database_session)`.

    Returns
    -------
    list[str]
        Alphabetically sorted case names.
    """
    names = db.query(distinct(Case.name)).order_by(Case.name).all()

    return [n[0] for n in names]


@case_router.get(
    "/{case_id}",
    response_model=CaseDetailOut,
    responses={
        200: {"description": "Case found."},
        404: {"description": "Case not found."},
        500: {"description": "Internal server error."},
    },
)
def get_case(
    case_id: UUID, db: Session = Depends(get_database_session)
) -> CaseDetailOut:
    """Retrieve a case by its unique identifier.

    Parameters
    ----------
    case_id : UUID
        The unique identifier of the case to retrieve.
    db : Session, optional
        The database session dependency, by default provided by
        `Depends(get_database_session)`.

    Returns
    -------
    CaseDetailOut
        The case object with nested simulation summaries if found.
    """
    case = (
        db.query(Case)
        .options(selectinload(Case.machine), selectinload(Case.executions))
        .options(selectinload(Case.links))
        .filter(Case.id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    resp = _case_to_detail_out(case)

    return resp


@case_router.patch(
    "/{case_id}",
    response_model=CaseDetailOut,
    responses={
        200: {"description": "Case updated successfully."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden."},
        404: {"description": "Case not found."},
        422: {"description": "Validation error."},
        500: {"description": "Internal server error."},
    },
)
def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> CaseDetailOut:
    """Partially update allowed user-managed case metadata fields."""
    if not can_edit_managed_content(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Editing case metadata requires SimBoard admin access or "
                "verified E3SM GitHub organization membership."
            ),
        )

    case = (
        db.query(Case)
        .options(
            selectinload(Case.machine),
            selectinload(Case.executions),
            selectinload(Case.links),
        )
        .filter(Case.id == case_id)
        .one_or_none()
    )

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    updates = payload.model_dump(by_alias=False, exclude_unset=True)
    updates.pop("links", None)
    for field, value in updates.items():
        setattr(case, field, value)

    if "links" in payload.model_fields_set:
        _replace_case_links(case, payload.links or [])

    case.updated_at = datetime.now(timezone.utc)

    with transaction(db):
        db.add(case)
        db.flush()

    db.expire_all()
    case_loaded = (
        db.query(Case)
        .options(
            selectinload(Case.machine),
            selectinload(Case.executions),
            selectinload(Case.links),
        )
        .filter(Case.id == case_id)
        .one_or_none()
    )

    if case_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load updated case.",
        )

    return _case_to_detail_out(case_loaded)


@simulation_router.post(
    "",
    response_model=SimulationOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Simulation created successfully."},
        400: {"description": "Invalid input."},
        401: {"description": "Unauthorized."},
        422: {"description": "Validation error."},
        500: {"description": "Internal server error."},
    },
)
def create_simulation(
    payload: SimulationCreate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """Create a new simulation record in the database."""
    now = datetime.now(timezone.utc)

    # Verify the case exists
    case = db.query(Case).filter(Case.id == payload.case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case '{payload.case_id}' not found.",
        )

    execution_data = payload.model_dump(
        by_alias=False,
        exclude={"artifacts", "links"},
        exclude_unset=True,
    )
    execution_data["status"] = ExecutionStatus(payload.status.value)
    sim = Execution(
        **execution_data,
        created_by=user.id,
        last_updated_by=user.id,
        created_at=now,
        updated_at=now,
    )

    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference="manual_simulation_create",
        machine_id=case.machine_id,
        triggered_by=user.id,
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        created_at=now,
        archive_sha256=None,
    )

    sim.ingestion = ingestion

    if payload.artifacts:
        sim.artifacts.extend(_build_artifact_models(payload.artifacts))

    if payload.links:
        sim.links.extend(_build_external_link_models(payload.links))

    with transaction(db):
        db.add(sim)
        db.flush()

    # Re-query with relationships loaded
    sim_loaded = (
        _execution_detail_query(db).filter(Execution.id == sim.id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load newly created simulation.",
        )

    result = _execution_to_legacy_out(sim_loaded)

    return result


@diagnostics_router.post(
    "/link",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Diagnostics linked successfully."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden."},
        404: {"description": "Matching case not found."},
        422: {"description": "Validation error."},
    },
)
def link_case_diagnostics(
    payload: DiagnosticsLinkRequest,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> None:
    """Resolve one case and upsert case-scoped diagnostic links."""
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and service accounts may link diagnostics.",
        )

    case_id = _resolve_case_id_for_diagnostics_link(
        db=db,
        case_name=payload.case_name,
        machine_name=payload.machine,
        hpc_username=payload.hpc_username,
    )
    _upsert_case_diagnostic_links(
        db=db,
        case_id=case_id,
        diagnostics=payload.diagnostics,
    )


@simulation_router.get(
    "",
    response_model=SimulationPageOut,
    responses={
        200: {"description": "List all simulations."},
        401: {"description": "Unauthorized."},
        500: {"description": "Internal server error."},
    },
)
def list_simulations(  # noqa: C901
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    case_id: UUID | None = Query(None),
    case_name: list[str] | None = Query(
        None,
        description="Filter simulations by exact case name.",
    ),
    case_group: list[str] | None = Query(
        None,
        description="Filter simulations by exact case group.",
    ),
    status_filter: list[SimulationStatus] | None = Query(None, alias="status"),
    simulation_type: list[SimulationType] | None = Query(None),
    machine_id: list[UUID] | None = Query(None),
    hpc_username: list[str] | None = Query(None),
    campaign: list[str] | None = Query(None),
    experiment_type: list[str] | None = Query(None),
    compset: list[str] | None = Query(None),
    grid_name: list[str] | None = Query(None),
    grid_resolution: list[str] | None = Query(None),
    initialization_type: list[str] | None = Query(None),
    compiler: list[str] | None = Query(None),
    git_tag: list[str] | None = Query(None),
    created_by: list[UUID] | None = Query(None),
    sort_by: str = Query(
        "created_at",
        pattern=(
            "^(created_at|updated_at|execution_id|case_name|case_hash|campaign|"
            "case_group|experiment_type|simulation_type|status|git_branch|git_tag|"
            "git_commit_hash|simulation_start_date|simulation_end_date|run_start_date|"
            "grid_resolution|compset|grid_name|machine_name)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> SimulationPageOut:
    """Return one lightweight, server-filtered simulation page."""
    query = (
        db.query(Execution)
        .join(Case, Case.id == Execution.case_id)
        .join(Machine, Machine.id == Case.machine_id)
    )

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Execution.execution_id.ilike(term),
                Case.name.ilike(term),
                Execution.git_branch.ilike(term),
                Execution.git_tag.ilike(term),
                Execution.git_commit_hash.ilike(term),
                Execution.grid_name.ilike(term),
                Execution.grid_resolution.ilike(term),
                Execution.compset.ilike(term),
                Execution.compset_alias.ilike(term),
                Machine.name.ilike(term),
            )
        )
    if case_id is not None:
        query = query.filter(Execution.case_id == case_id)
    if case_name:
        query = query.filter(Case.name.in_(case_name))
    if case_group:
        query = query.filter(Case.case_group.in_(case_group))
    if status_filter:
        query = query.filter(
            Execution.status.in_(
                [ExecutionStatus(value.value) for value in status_filter]
            )
        )
    if simulation_type:
        query = query.filter(Execution.simulation_type.in_(simulation_type))
    if machine_id:
        query = query.filter(Case.machine_id.in_(machine_id))
    if hpc_username:
        query = query.filter(Case.hpc_username.in_(hpc_username))
    for column, values in (
        (Execution.campaign, campaign),
        (Execution.experiment_type, experiment_type),
        (Execution.compset, compset),
        (Execution.grid_name, grid_name),
        (Execution.grid_resolution, grid_resolution),
        (Execution.initialization_type, initialization_type),
        (Execution.compiler, compiler),
        (Execution.git_tag, git_tag),
        (Execution.created_by, created_by),
    ):
        if values:
            query = query.filter(column.in_(values))

    total = query.order_by(None).count()
    rows_query = query.with_entities(
        Execution.id,
        Execution.case_id,
        Case.name.label("case_name"),
        Case.case_group,
        Execution.execution_id,
        Execution.case_hash,
        Execution.simulation_type,
        Execution.status,
        Execution.campaign,
        Execution.experiment_type,
        Execution.compset,
        Execution.compset_alias,
        Execution.grid_name,
        Execution.grid_resolution,
        Execution.initialization_type,
        Execution.simulation_start_date,
        Execution.simulation_end_date,
        Execution.run_start_date,
        Execution.run_end_date,
        Execution.compiler,
        Execution.compute_type,
        Execution.git_branch,
        Execution.git_tag,
        Execution.git_commit_hash,
        Case.machine_id,
        Machine.name.label("machine_name"),
        Case.hpc_username,
        Execution.created_by,
        Execution.last_updated_by,
        Execution.created_at,
        Execution.updated_at,
    )
    sort_column = {
        "created_at": Execution.created_at,
        "updated_at": Execution.updated_at,
        "execution_id": Execution.execution_id,
        "case_name": Case.name,
        "case_group": Case.case_group,
        "case_hash": Execution.case_hash,
        "campaign": Execution.campaign,
        "experiment_type": Execution.experiment_type,
        "simulation_type": Execution.simulation_type,
        "status": Execution.status,
        "git_branch": Execution.git_branch,
        "git_tag": Execution.git_tag,
        "git_commit_hash": Execution.git_commit_hash,
        "simulation_start_date": Execution.simulation_start_date,
        "simulation_end_date": Execution.simulation_end_date,
        "run_start_date": Execution.run_start_date,
        "grid_resolution": Execution.grid_resolution,
        "compset": Execution.compset,
        "grid_name": Execution.grid_name,
        "machine_name": Machine.name,
    }[sort_by]
    ordering = asc(sort_column) if sort_order == "asc" else desc(sort_column)
    rows = (
        rows_query.order_by(ordering, Execution.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return SimulationPageOut(
        items=[SimulationListItemOut(**row._asdict()) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@simulation_router.get("/filter-options", response_model=SimulationFilterOptionsOut)
def get_simulation_filter_options(
    db: Session = Depends(get_database_session),
) -> SimulationFilterOptionsOut:
    """Return distinct scalar simulation filter values."""
    return SimulationFilterOptionsOut(
        case_names=_distinct_values(db, Case.name),
        case_groups=_distinct_values(db, Case.case_group),
        machine_ids=_distinct_values(db, Case.machine_id),
        machines=_machine_filter_options(db),
        hpc_usernames=_distinct_values(db, Case.hpc_username),
        campaigns=_distinct_values(db, Execution.campaign),
        experiment_types=_distinct_values(db, Execution.experiment_type),
        compsets=_distinct_values(db, Execution.compset),
        grid_names=_distinct_values(db, Execution.grid_name),
        grid_resolutions=_distinct_values(db, Execution.grid_resolution),
        simulation_types=_distinct_values(db, Execution.simulation_type),
        initialization_types=_distinct_values(db, Execution.initialization_type),
        compilers=_distinct_values(db, Execution.compiler),
        statuses=_distinct_values(db, Execution.status),
        git_tags=_distinct_values(db, Execution.git_tag),
        created_by_ids=_distinct_values(db, Execution.created_by),
        creators=_creator_filter_options(db),
    )


@simulation_router.patch(
    "/{sim_id}",
    response_model=SimulationOut,
    responses={
        200: {"description": "Simulation updated successfully."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden."},
        404: {"description": "Simulation not found."},
        422: {"description": "Validation error."},
        500: {"description": "Internal server error."},
    },
)
def update_simulation(
    sim_id: UUID,
    payload: SimulationUpdate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> SimulationOut:
    """Partially update allowed user-managed simulation fields."""
    if not can_edit_managed_content(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Editing simulation metadata requires SimBoard admin access or "
                "verified E3SM GitHub organization membership."
            ),
        )

    sim = db.query(Execution).filter(Execution.id == sim_id).one_or_none()

    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    now = datetime.now(timezone.utc)
    updates = payload.model_dump(by_alias=False, exclude_unset=True)
    updates.pop("artifacts", None)
    updates.pop("links", None)

    for field, value in updates.items():
        if field == "status":
            value = ExecutionStatus(value.value)
        setattr(sim, field, value)

    if "artifacts" in payload.model_fields_set:
        sim.artifacts = _build_artifact_models(payload.artifacts or [])

    if "links" in payload.model_fields_set:
        sim.links = _build_external_link_models(payload.links or [])

    sim.last_updated_by = user.id
    sim.updated_at = now

    with transaction(db):
        db.add(sim)
        db.flush()

    db.expire_all()
    sim_loaded = (
        _execution_detail_query(db).filter(Execution.id == sim_id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load updated simulation.",
        )

    return _execution_to_legacy_out(sim_loaded)


def _resolve_case_id_for_diagnostics_link(
    *,
    db: Session,
    case_name: str,
    machine_name: str,
    hpc_username: str,
) -> UUID:
    """Resolve a unique case ID from case, machine, and HPC username."""
    machine = resolve_machine_by_name(db, machine_name)

    if machine is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No case matched the provided case_name, machine, and hpc_username.",
        )

    match = (
        db.query(Case.id)
        .filter(Case.name == case_name)
        .filter(Case.machine_id == machine.id)
        .filter(Case.hpc_username == hpc_username)
        .one_or_none()
    )

    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No case matched the provided case_name, machine, and hpc_username.",
        )

    return match[0]


def _upsert_case_diagnostic_links(
    *,
    db: Session,
    case_id: UUID,
    diagnostics: list,
) -> None:
    """Create or update case-owned diagnostic links idempotently."""
    now = datetime.now(timezone.utc)

    with transaction(db):
        for diagnostic in diagnostics:
            stmt = (
                pg_insert(ExternalLink)
                .values(
                    case_id=case_id,
                    kind=ExternalLinkKind.DIAGNOSTIC,
                    url=str(diagnostic.url),
                    label=diagnostic.name,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[
                        ExternalLink.case_id,
                        ExternalLink.kind,
                        ExternalLink.url,
                    ],
                    index_where=ExternalLink.case_id.is_not(None),
                    set_={
                        "label": diagnostic.name,
                        "updated_at": now,
                    },
                )
            )
            db.execute(stmt)


@simulation_router.get(
    "/{sim_id}",
    response_model=SimulationOut,
    responses={
        200: {"description": "Simulation found."},
        401: {"description": "Unauthorized."},
        404: {"description": "Simulation not found."},
        500: {"description": "Internal server error."},
    },
)
def get_simulation(sim_id: UUID, db: Session = Depends(get_database_session)):
    """Retrieve a simulation by its unique identifier.

    Parameters
    ----------
    sim_id : UUID
        The unique identifier of the simulation to retrieve.
    db : Session, optional
        The database session dependency, by default provided by
        `Depends(get_database_session)`.

    Returns
    -------
    Simulation
        The simulation object if found.

    Raises
    ------
    HTTPException
        If the simulation with the given ID is not found, raises a 404 HTTP exception.
    """
    sim = _execution_detail_query(db).filter(Execution.id == sim_id).one_or_none()

    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    return _execution_to_legacy_out(sim)


def _build_case_summary(case: Case) -> dict:
    """Build shared summary data for case response schemas."""
    summaries = []
    machine_names = sorted(
        {case.machine.name}
        if case.machine is not None and case.machine.name
        else set(),
        key=lambda name: name.lower(),
    )
    hpc_usernames = sorted(
        {case.hpc_username} if case.hpc_username else set(),
        key=lambda username: username.lower(),
    )

    for sim in case.executions:
        summaries.append(
            SimulationSummaryOut(
                id=sim.id,
                execution_id=sim.execution_id,
                case_hash=sim.case_hash,
                compute_type=sim.compute_type,
                status=sim.status,
                simulation_start_date=sim.simulation_start_date,
                simulation_end_date=sim.simulation_end_date,
            )
        )

    return {
        "id": case.id,
        "name": case.name,
        "case_group": case.case_group,
        "simulations": summaries,
        "machine_names": machine_names,
        "hpc_usernames": hpc_usernames,
        "links": [_external_link_to_out(link) for link in case.links],
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }


def _case_to_summary_out(case: Case) -> CaseSummaryOut:
    """Convert a Case ORM instance to CaseSummaryOut with nested summaries.

    Parameters
    ----------
    case : Case
        The Case ORM instance to convert.

    Returns
    -------
    CaseSummaryOut
        The corresponding CaseSummaryOut schema instance with nested
        SimulationSummaryOut
    """
    result = CaseSummaryOut(**_build_case_summary(case))

    return result


def _distinct_values(db: Session, column) -> list:
    """Return sorted non-null scalar values for a filter-option column."""
    return [
        value
        for (value,) in db.query(distinct(column))
        .filter(column.is_not(None))
        .order_by(column)
        .all()
    ]


def _machine_filter_options(db: Session) -> list[FilterOptionOut]:
    """Return machines referenced by catalog cases with display names."""
    rows = (
        db.query(Machine.id, Machine.name)
        .join(Case, Case.machine_id == Machine.id)
        .distinct()
        .order_by(Machine.name, Machine.id)
        .all()
    )
    return [
        FilterOptionOut(value=str(machine_id), label=name) for machine_id, name in rows
    ]


def _creator_filter_options(db: Session) -> list[FilterOptionOut]:
    """Return simulation creators with stable IDs and email labels."""
    rows = (
        db.query(User.id, User.email)
        .join(Execution, Execution.created_by == User.id)
        .distinct()
        .order_by(User.email, User.id)
        .all()
    )
    return [FilterOptionOut(value=str(user_id), label=email) for user_id, email in rows]


def _case_to_detail_out(case: Case) -> CaseDetailOut:
    """Convert a Case ORM instance to CaseDetailOut."""
    result = CaseDetailOut(
        **_build_case_summary(case),
        description=case.description,
        key_features=case.key_features,
        known_issues=case.known_issues,
        notes_markdown=case.notes_markdown,
    )

    return result


def _build_artifact_models(artifacts: list) -> list[Artifact]:
    models: list[Artifact] = []

    for artifact in artifacts:
        artifact_data = artifact.model_dump(by_alias=False, exclude_unset=True)
        artifact_data["uri"] = str(artifact.uri)
        models.append(Artifact(**artifact_data))

    return models


def _build_external_link_models(links: list) -> list[ExternalLink]:
    models: list[ExternalLink] = []

    for link in links:
        link_data = link.model_dump(by_alias=False, exclude_unset=True)
        link_data["url"] = str(link.url)
        models.append(ExternalLink(**link_data))

    return models


def _replace_case_links(case: Case, links: list) -> None:
    existing_by_key = {(link.kind, link.url): link for link in case.links}
    next_links: list[ExternalLink] = []

    for link in links:
        link_data = link.model_dump(by_alias=False, exclude_unset=True)
        link_data["url"] = str(link.url)
        key = (link_data["kind"], link_data["url"])
        existing = existing_by_key.pop(key, None)

        if existing is not None:
            existing.label = link_data.get("label")
            next_links.append(existing)
            continue

        next_links.append(ExternalLink(**link_data))

    case.links = next_links


def _external_link_to_out(link: ExternalLink) -> dict:
    owner_type = "simulation" if link.simulation_id is not None else "case"

    return {
        "id": link.id,
        "kind": link.kind,
        "url": link.url,
        "label": link.label,
        "owner_type": owner_type,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def _execution_detail_query(db: Session):
    return db.query(Execution).options(
        joinedload(Execution.case).joinedload(Case.machine),
        joinedload(Execution.case).selectinload(Case.links),
        selectinload(Execution.artifacts),
        selectinload(Execution.links),
    )


def _execution_to_legacy_out(sim: Execution) -> SimulationOut:
    """Convert a Execution ORM instance to a SimulationOut schema.

    Derives ``case_name`` and ``case_group`` from the associated Case relationship.

    Parameters
    ----------
    sim : Execution
        The Execution ORM instance to convert.

    Returns
    -------
    SimulationOut
        The corresponding SimulationOut schema instance with additional derived
        fields.
    """
    case = sim.case
    llm_available = is_summary_llm_available()
    merged_links = merge_execution_and_case_links(sim.links, case.links)
    serialized_links = [_external_link_to_out(link) for link in merged_links]

    result = SimulationOut.model_validate(
        {
            **{k: v for k, v in sim.__dict__.items() if not k.startswith("_")},
            "case_name": case.name,
            "case_group": case.case_group,
            "machine_id": case.machine_id,
            "hpc_username": case.hpc_username,
            "machine": case.machine,
            "links": serialized_links,
            "summary_capabilities": SimulationSummaryCapabilitiesOut(
                llm_available=llm_available,
                auto_generate_deterministic_on_load=not llm_available,
            ),
        },
        from_attributes=True,
    )

    return result
