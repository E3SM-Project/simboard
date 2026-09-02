from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, asc, desc, distinct, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload, lazyload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.assistant.orchestrator import is_summary_llm_available
from app.features.catalog.enums import (
    ArtifactKind,
    ExecutionStatus,
    ExternalLinkKind,
    SimulationType,
)
from app.features.catalog.history import EntityType, changed_metadata, snapshot_metadata
from app.features.catalog.link_utils import merge_execution_and_case_links
from app.features.catalog.models import (
    Artifact,
    Case,
    DiagnosticProvenanceState,
    Execution,
    ExternalLink,
    MetadataChange,
)
from app.features.catalog.schemas import (
    CaseDetailOut,
    CaseExecutionArtifactOut,
    CaseFilterOptionsOut,
    CaseListItemOut,
    CasePageOut,
    CaseSummaryOut,
    CaseUpdate,
    CatalogOverviewOut,
    DiagnosticProvenanceStateOut,
    DiagnosticsLinkRequest,
    DiagnosticsScannerLinkRequest,
    ExecutionCreate,
    ExecutionExternalLinkOut,
    ExecutionFilterOptionsOut,
    ExecutionListItemOut,
    ExecutionOut,
    ExecutionPageOut,
    ExecutionSummaryCapabilitiesOut,
    ExecutionSummaryOut,
    ExecutionUpdate,
    FilterOptionOut,
    MetadataHistoryPageOut,
)
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.machine.utils import resolve_machine_by_name
from app.features.user.manager import can_edit_managed_content, current_active_user
from app.features.user.models import User, UserRole

execution_router = APIRouter(prefix="/executions", tags=["Executions"])
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
def list_cases(
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    name: str | None = Query(None),
    case_group: str | None = Query(None),
    machine_id: UUID | None = Query(None),
    hpc_username: str | None = Query(None),
    execution_id: str | None = Query(None),
    status_filter: ExecutionStatus | None = Query(None, alias="status"),
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
            "execution_count|latest_run_activity)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> CasePageOut:
    """Return one lightweight, server-filtered case page."""
    query = _filtered_case_list_query(
        db,
        search=search,
        name=name,
        case_group=case_group,
        machine_id=machine_id,
        hpc_username=hpc_username,
        execution_id=execution_id,
        status_filter=status_filter,
        simulation_type=simulation_type,
        campaign=campaign,
        initialization_type=initialization_type,
        compiler=compiler,
        git_tag=git_tag,
        created_by=created_by,
    )
    total = query.order_by(None).count()
    latest_execution = _completed_execution_summary_subquery(db)
    execution_count = _case_execution_count_subquery(db)
    rows_query = _case_list_projection(query, execution_count, latest_execution)
    ordering = _case_list_ordering(
        sort_by, sort_order, execution_count, latest_execution
    )
    rows = (
        rows_query.order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CasePageOut(
        items=[_case_list_item_from_row(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _filtered_case_list_query(
    db: Session,
    *,
    search: str | None,
    name: str | None,
    case_group: str | None,
    machine_id: UUID | None,
    hpc_username: str | None,
    execution_id: str | None,
    status_filter: ExecutionStatus | None,
    simulation_type: SimulationType | None,
    campaign: str | None,
    initialization_type: str | None,
    compiler: str | None,
    git_tag: str | None,
    created_by: UUID | None,
):
    """Apply the Case list's scalar and same-execution filters."""
    query = db.query(Case)
    if search:
        query = query.filter(Case.name.ilike(f"%{search.strip()}%"))
    for column, value in (
        (Case.name, name),
        (Case.case_group, case_group),
        (Case.machine_id, machine_id),
        (Case.hpc_username, hpc_username),
    ):
        if value:
            query = query.filter(column == value)

    predicates: list[ColumnElement[bool]] = []
    if execution_id:
        predicates.append(Execution.execution_id.ilike(f"%{execution_id.strip()}%"))
    if status_filter:
        predicates.append(Execution.status == ExecutionStatus(status_filter.value))
    if simulation_type:
        predicates.append(Execution.simulation_type == simulation_type)
    for column, value in (
        (Execution.campaign, campaign),
        (Execution.initialization_type, initialization_type),
        (Execution.compiler, compiler),
        (Execution.git_tag, git_tag),
        (Execution.created_by, created_by),
    ):
        if value is not None:
            predicates.append(column == value)
    if predicates:
        query = query.filter(Case.executions.any(and_(*predicates)))
    return query


def _case_execution_count_subquery(db: Session):
    """Return the per-case execution count correlated to a Case row."""
    return (
        db.query(func.count(Execution.id))
        .filter(Execution.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
    )


def _completed_execution_summary_subquery(db: Session):
    """Rank completed runs by actual activity, never audit timestamps."""
    latest_run_activity = func.coalesce(
        Execution.run_end_date, Execution.run_start_date
    )
    return (
        db.query(
            Execution.case_id.label("case_id"),
            Execution.execution_id.label("latest_execution_id"),
            Execution.status.label("latest_execution_status"),
            Execution.run_start_date.label("latest_run_start_date"),
            Execution.run_end_date.label("latest_run_end_date"),
            latest_run_activity.label("latest_run_activity"),
            func.row_number()
            .over(
                partition_by=Execution.case_id,
                order_by=(
                    latest_run_activity.desc().nullslast(),
                    Execution.run_end_date.desc().nullslast(),
                    Execution.run_start_date.desc().nullslast(),
                    Execution.execution_id.desc(),
                ),
            )
            .label("latest_execution_rank"),
        )
        .filter(Execution.status == ExecutionStatus.COMPLETED)
        .subquery()
    )


def _case_list_projection(query, execution_count, latest_execution):
    """Attach the list projection and optional completed-run summary."""
    return (
        query.join(Case.machine)
        .outerjoin(
            latest_execution,
            and_(
                latest_execution.c.case_id == Case.id,
                latest_execution.c.latest_execution_rank == 1,
            ),
        )
        .with_entities(
            Case.id,
            Case.name,
            Case.case_group,
            Case.machine_id,
            Machine.name.label("machine_name"),
            Case.hpc_username,
            execution_count.label("execution_count"),
            Case.created_at,
            Case.updated_at,
            latest_execution.c.latest_execution_id,
            latest_execution.c.latest_execution_status,
            latest_execution.c.latest_run_start_date,
            latest_execution.c.latest_run_end_date,
            latest_execution.c.latest_run_activity,
        )
    )


def _case_list_ordering(
    sort_by: str, sort_order: str, execution_count, latest_execution
):
    """Build nullable case-list ordering with a stable Case ID tiebreaker."""
    sort_column = {
        "updated_at": Case.updated_at,
        "created_at": Case.created_at,
        "name": Case.name,
        "case_group": Case.case_group,
        "machine_name": Machine.name,
        "hpc_username": Case.hpc_username,
        "execution_count": execution_count,
        "latest_run_activity": latest_execution.c.latest_run_activity,
    }[sort_by]
    ordering = (
        asc(sort_column).nullslast()
        if sort_order == "asc"
        else desc(sort_column).nullslast()
    )
    return ordering, Case.id.asc()


def _case_list_item_from_row(row) -> CaseListItemOut:
    """Build a case row, nesting the optional run-derived execution summary."""
    values = row._asdict()
    execution_id = values.pop("latest_execution_id", None)
    status = values.pop("latest_execution_status", None)
    run_start_date = values.pop("latest_run_start_date", None)
    run_end_date = values.pop("latest_run_end_date", None)
    values.pop("latest_run_activity", None)

    if status is not None:
        values["latest_execution"] = {
            "execution_id": execution_id,
            "status": status,
            "run_start_date": run_start_date,
            "run_end_date": run_end_date,
        }

    return CaseListItemOut(**values)


@case_router.get("/overview", response_model=CatalogOverviewOut)
def get_catalog_overview(
    db: Session = Depends(get_database_session),
) -> CatalogOverviewOut:
    """Return fixed-size aggregate data used by homepage."""
    total_cases = db.query(func.count(Case.id)).scalar() or 0
    total_executions = db.query(func.count(Execution.id)).scalar() or 0
    latest_submission = db.query(func.max(Execution.created_at)).scalar()
    machine_count_rows = (
        db.query(Case.machine_id, func.count(Case.id)).group_by(Case.machine_id).all()
    )
    machine_counts: dict[UUID, int] = {
        machine_id: count for machine_id, count in machine_count_rows
    }
    execution_count = (
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
            execution_count.label("execution_count"),
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
        total_executions=total_executions,
        latest_submission=latest_submission,
        machine_counts=machine_counts,
        recent_cases=[CaseListItemOut(**row._asdict()) for row in rows],
    )


@case_router.get("/filter-options", response_model=CaseFilterOptionsOut)
def get_case_filter_options(
    db: Session = Depends(get_database_session),
    search: str | None = Query(None),
    name: str | None = Query(None),
    case_group: str | None = Query(None),
    machine_id: UUID | None = Query(None),
    hpc_username: str | None = Query(None),
    execution_id: str | None = Query(None),
    status_filter: ExecutionStatus | None = Query(None, alias="status"),
    simulation_type: SimulationType | None = Query(None),
    campaign: str | None = Query(None),
    initialization_type: str | None = Query(None),
    compiler: str | None = Query(None),
    git_tag: str | None = Query(None),
    created_by: UUID | None = Query(None),
) -> CaseFilterOptionsOut:
    """Return scalar case facets constrained by all other active filters."""
    filters = {
        "search": search,
        "name": name,
        "case_group": case_group,
        "machine_id": machine_id,
        "hpc_username": hpc_username,
        "execution_id": execution_id,
        "status": status_filter,
        "simulation_type": simulation_type,
        "campaign": campaign,
        "initialization_type": initialization_type,
        "compiler": compiler,
        "git_tag": git_tag,
        "created_by": created_by,
    }

    def case_query(exclude: str):
        return _filtered_cases_for_facets(db, filters, exclude=exclude)

    def execution_query(exclude: str):
        return _filtered_executions_for_facets(db, filters, exclude=exclude)

    return CaseFilterOptionsOut(
        names=_distinct_query_values(case_query("name"), Case.name),
        case_groups=_distinct_query_values(case_query("case_group"), Case.case_group),
        hpc_usernames=_distinct_query_values(
            case_query("hpc_username"), Case.hpc_username
        ),
        machine_ids=_distinct_query_values(case_query("machine_id"), Case.machine_id),
        machines=_machine_filter_options_for_query(case_query("machine_id")),
        statuses=_distinct_query_values(execution_query("status"), Execution.status),
        simulation_types=_distinct_query_values(
            execution_query("simulation_type"), Execution.simulation_type
        ),
        campaigns=_distinct_query_values(
            execution_query("campaign"), Execution.campaign
        ),
        initialization_types=_distinct_query_values(
            execution_query("initialization_type"), Execution.initialization_type
        ),
        compilers=_distinct_query_values(
            execution_query("compiler"), Execution.compiler
        ),
        git_tags=_distinct_query_values(execution_query("git_tag"), Execution.git_tag),
        created_by_ids=_distinct_query_values(
            execution_query("created_by"), Execution.created_by
        ),
        creators=_creator_filter_options_for_query(execution_query("created_by")),
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

    This lightweight endpoint avoids loading nested execution data,
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
    "/resolve",
    response_model=CaseDetailOut,
    responses={
        200: {"description": "Case found."},
        404: {"description": "Case not found."},
        500: {"description": "Internal server error."},
    },
)
def resolve_case(
    machine: str,
    hpc_username: str,
    case_name: str,
    db: Session = Depends(get_database_session),
) -> CaseDetailOut:
    """Retrieve a case by its immutable human-readable identity."""
    case = _get_case_by_identity(
        db=db,
        machine_name=machine,
        hpc_username=hpc_username,
        case_name=case_name,
    )

    return _case_to_detail_out(case)


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
        The case object with nested execution summaries if found.
    """
    return _case_to_detail_out(_get_case(case_id, db))


@case_router.get(
    "/{case_id}/history",
    response_model=MetadataHistoryPageOut,
    responses={
        200: {"description": "Case metadata history found."},
        404: {"description": "Case not found."},
    },
)
def get_case_history(
    case_id: UUID,
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> MetadataHistoryPageOut:
    """Return reverse-chronological managed metadata history for one case."""
    if db.query(Case.id).filter(Case.id == case_id).first() is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return _get_metadata_history(
        db,
        entity_type="case",
        entity_id=case_id,
        page=page,
        page_size=page_size,
    )


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

    with transaction(db):
        case = (
            db.query(Case)
            .options(lazyload("*"), selectinload(Case.links))
            .filter(Case.id == case_id)
            .with_for_update()
            .one_or_none()
        )

        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")

        audit_fields = set(payload.model_fields_set) - {"edit_reason"}
        previous_metadata = snapshot_metadata(case, audit_fields)
        updates = payload.model_dump(by_alias=False, exclude_unset=True)
        updates.pop("edit_reason", None)
        updates.pop("links", None)
        for field, value in updates.items():
            setattr(case, field, value)

        if "links" in payload.model_fields_set:
            _replace_case_links(case, payload.links or [])

        current_metadata = snapshot_metadata(case, audit_fields)
        changes = changed_metadata(previous_metadata, current_metadata)
        if changes:
            now = datetime.now(timezone.utc)
            case.updated_at = now
            db.add(case)
            db.add_all(
                [
                    MetadataChange(
                        entity_type="case",
                        entity_id=case.id,
                        field_name=field_name,
                        old_value=old_value,
                        new_value=new_value,
                        editor_id=user.id,
                        changed_at=now,
                        reason=payload.edit_reason,
                    )
                    for field_name, old_value, new_value in changes
                ]
            )
            db.flush()
        else:
            db.rollback()

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


@execution_router.post(
    "",
    response_model=ExecutionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Execution created successfully."},
        400: {"description": "Invalid input."},
        401: {"description": "Unauthorized."},
        422: {"description": "Validation error."},
        500: {"description": "Internal server error."},
    },
)
def create_execution(
    payload: ExecutionCreate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> ExecutionOut:
    """Create a new execution record."""
    execution = _create_execution(
        payload,
        db,
        user,
        entity_label="execution",
    )
    return _execution_to_out(execution)


def _create_execution(
    payload: ExecutionCreate,
    db: Session,
    user: User,
    *,
    entity_label: str,
) -> Execution:
    """Persist one execution."""
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
    execution = Execution(
        **execution_data,
        created_by=user.id,
        last_updated_by=user.id,
        created_at=now,
        updated_at=now,
    )

    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference=f"manual_{entity_label}_create",
        machine_id=case.machine_id,
        triggered_by=user.id,
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        created_at=now,
        archive_sha256=None,
    )

    execution.ingestion = ingestion

    if payload.artifacts:
        execution.artifacts.extend(_build_artifact_models(payload.artifacts))

    if payload.links:
        execution.links.extend(_build_external_link_models(payload.links))

    with transaction(db):
        db.add(execution)
        db.flush()

    # Re-query with relationships loaded
    sim_loaded = (
        _execution_detail_query(db).filter(Execution.id == execution.id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load newly created {entity_label}.",
        )

    return sim_loaded


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


@diagnostics_router.get(
    "/scanner-state", response_model=DiagnosticProvenanceStateOut | None
)
def get_diagnostics_scanner_state(
    machine: str,
    archive_relative_case_path: str,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> DiagnosticProvenanceStateOut | None:
    """Return successful scanner state for one machine/archive case path."""
    _require_diagnostics_scanner_role(user)
    resolved_machine = resolve_machine_by_name(db, machine)

    if resolved_machine is None:
        raise HTTPException(status_code=404, detail="Unknown machine.")

    state = (
        db.query(DiagnosticProvenanceState)
        .filter(DiagnosticProvenanceState.machine_name == resolved_machine.name)
        .filter(
            DiagnosticProvenanceState.archive_relative_case_path
            == archive_relative_case_path
        )
        .one_or_none()
    )

    return DiagnosticProvenanceStateOut.model_validate(state) if state else None


@diagnostics_router.post("/scanner/link", status_code=status.HTTP_204_NO_CONTENT)
def link_scanner_diagnostics(
    payload: DiagnosticsScannerLinkRequest,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> None:
    """Atomically upsert one scanner-managed case diagnostic link and state."""
    _require_diagnostics_scanner_role(user)

    if len(payload.diagnostics) != 1:
        raise HTTPException(
            status_code=422, detail="Scanner payload requires one diagnostic."
        )

    if _unsafe_archive_relative_path(payload.provenance.archive_relative_case_path):
        raise HTTPException(
            status_code=422, detail="Invalid archive-relative case path."
        )

    machine = resolve_machine_by_name(db, payload.machine)
    if machine is None:
        raise HTTPException(status_code=404, detail="No matching case found.")

    case_id = _resolve_case_id_for_diagnostics_link(
        db=db,
        case_name=payload.case_name,
        machine_name=payload.machine,
        hpc_username=payload.hpc_username,
    )
    diagnostic = payload.diagnostics[0]
    now = datetime.now(timezone.utc)

    with transaction(db):
        link_id = db.execute(
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
                set_={"label": diagnostic.name, "updated_at": now},
            )
            .returning(ExternalLink.id)
        ).scalar_one()
        db.execute(
            pg_insert(DiagnosticProvenanceState)
            .values(
                link_id=link_id,
                machine_name=machine.name,
                archive_relative_case_path=payload.provenance.archive_relative_case_path,
                settings_filename=payload.provenance.settings_filename,
                provenance_timestamp=payload.provenance.provenance_timestamp,
                fingerprint=payload.provenance.fingerprint,
                linked_url=str(diagnostic.url),
                submitted_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_diagnostic_provenance_states_machine_path",
                set_={
                    "link_id": link_id,
                    "settings_filename": payload.provenance.settings_filename,
                    "provenance_timestamp": payload.provenance.provenance_timestamp,
                    "fingerprint": payload.provenance.fingerprint,
                    "linked_url": str(diagnostic.url),
                    "submitted_at": now,
                },
            )
        )


@execution_router.get(
    "",
    response_model=ExecutionPageOut,
    responses={
        200: {"description": "List all executions."},
        401: {"description": "Unauthorized."},
        500: {"description": "Internal server error."},
    },
)
def list_executions(  # noqa: C901
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    case_id: UUID | None = Query(None),
    case_name: list[str] | None = Query(
        None,
        description="Filter executions by exact case name.",
    ),
    case_group: list[str] | None = Query(
        None,
        description="Filter executions by exact case group.",
    ),
    status_filter: list[ExecutionStatus] | None = Query(None, alias="status"),
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
            "git_commit_hash|simulation_start_date|simulation_end_date|run_start_date|run_activity|"
            "grid_resolution|compset|grid_name|machine_name)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> ExecutionPageOut:
    """Return one lightweight, server-filtered execution page."""
    return _list_executions(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        case_id=case_id,
        case_name=case_name,
        case_group=case_group,
        status_filter=status_filter,
        simulation_type=simulation_type,
        machine_id=machine_id,
        hpc_username=hpc_username,
        campaign=campaign,
        experiment_type=experiment_type,
        compset=compset,
        grid_name=grid_name,
        grid_resolution=grid_resolution,
        initialization_type=initialization_type,
        compiler=compiler,
        git_tag=git_tag,
        created_by=created_by,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@execution_router.get(
    "/filter-options",
    response_model=ExecutionFilterOptionsOut,
)
def get_execution_filter_options(
    db: Session = Depends(get_database_session),
) -> ExecutionFilterOptionsOut:
    """Return distinct scalar execution filter values."""
    return _get_execution_filter_options(db)


@execution_router.get(
    "/resolve",
    response_model=ExecutionOut,
    responses={
        200: {"description": "Execution found."},
        404: {"description": "Execution not found."},
        500: {"description": "Internal server error."},
    },
)
def resolve_execution(
    machine: str,
    hpc_username: str,
    case_name: str,
    execution_id: str,
    db: Session = Depends(get_database_session),
) -> ExecutionOut:
    """Retrieve an execution by its immutable human-readable identity."""
    case = _get_case_by_identity(
        db=db,
        machine_name=machine,
        hpc_username=hpc_username,
        case_name=case_name,
    )
    execution = (
        _execution_detail_query(db)
        .filter(Execution.case_id == case.id)
        .filter(Execution.execution_id == execution_id)
        .one_or_none()
    )

    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return _execution_to_out(execution)


@execution_router.get(
    "/{execution_id}",
    response_model=ExecutionOut,
    responses={
        200: {"description": "Execution found."},
        401: {"description": "Unauthorized."},
        404: {"description": "Execution not found."},
        500: {"description": "Internal server error."},
    },
)
def get_execution(
    execution_id: UUID,
    db: Session = Depends(get_database_session),
) -> ExecutionOut:
    """Retrieve an execution by its unique identifier."""
    execution = _get_execution(execution_id, db, entity_label="execution")
    return _execution_to_out(execution)


@execution_router.get(
    "/{execution_id}/history",
    response_model=MetadataHistoryPageOut,
    responses={
        200: {"description": "Execution metadata history found."},
        404: {"description": "Execution not found."},
    },
)
def get_execution_history(
    execution_id: UUID,
    db: Session = Depends(get_database_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> MetadataHistoryPageOut:
    """Return reverse-chronological managed metadata history for one execution."""
    if db.query(Execution.id).filter(Execution.id == execution_id).first() is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return _get_metadata_history(
        db,
        entity_type="execution",
        entity_id=execution_id,
        page=page,
        page_size=page_size,
    )


def _list_executions(  # noqa: C901
    db: Session,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    case_id: UUID | None = Query(None),
    case_name: list[str] | None = Query(
        None,
        description="Filter executions by exact case name.",
    ),
    case_group: list[str] | None = Query(
        None,
        description="Filter executions by exact case group.",
    ),
    status_filter: list[ExecutionStatus] | None = Query(None, alias="status"),
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
            "git_commit_hash|simulation_start_date|simulation_end_date|run_start_date|run_activity|"
            "grid_resolution|compset|grid_name|machine_name)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> ExecutionPageOut:
    """Build one lightweight, server-filtered execution page."""
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
        query = query.filter(Execution.status.in_(status_filter))
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
        "run_activity": func.coalesce(Execution.run_end_date, Execution.run_start_date),
        "grid_resolution": Execution.grid_resolution,
        "compset": Execution.compset,
        "grid_name": Execution.grid_name,
        "machine_name": Machine.name,
    }[sort_by]
    ordering = asc(sort_column) if sort_order == "asc" else desc(sort_column)
    if sort_by == "run_activity":
        ordering = ordering.nullslast()
    rows = (
        rows_query.order_by(ordering, Execution.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ExecutionPageOut(
        items=[ExecutionListItemOut(**row._asdict()) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _get_execution_filter_options(db: Session) -> ExecutionFilterOptionsOut:
    """Build distinct scalar execution filter values."""
    return ExecutionFilterOptionsOut(
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


@execution_router.patch(
    "/{execution_id}",
    response_model=ExecutionOut,
    responses={
        200: {"description": "Execution updated successfully."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden."},
        404: {"description": "Execution not found."},
        422: {"description": "Validation error."},
        500: {"description": "Internal server error."},
    },
)
def update_execution(
    execution_id: UUID,
    payload: ExecutionUpdate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> ExecutionOut:
    """Partially update allowed user-managed execution fields."""
    execution = _update_execution(
        execution_id,
        payload,
        db,
        user,
        entity_label="execution",
    )
    return _execution_to_out(execution)


def _update_execution(
    execution_id: UUID,
    payload: ExecutionUpdate,
    db: Session,
    user: User,
    *,
    entity_label: str,
) -> Execution:
    """Update one execution."""
    if not can_edit_managed_content(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Editing {entity_label} metadata requires SimBoard admin access or "
                "verified E3SM GitHub organization membership."
            ),
        )

    with transaction(db):
        execution = (
            db.query(Execution)
            .options(
                lazyload("*"),
                selectinload(Execution.artifacts),
                selectinload(Execution.links),
            )
            .filter(Execution.id == execution_id)
            .with_for_update()
            .one_or_none()
        )

        if execution is None:
            raise HTTPException(
                status_code=404,
                detail=f"{entity_label.capitalize()} not found",
            )

        audit_fields = set(payload.model_fields_set) - {"edit_reason"}
        previous_metadata = snapshot_metadata(execution, audit_fields)
        updates = payload.model_dump(by_alias=False, exclude_unset=True)
        updates.pop("edit_reason", None)
        updates.pop("artifacts", None)
        updates.pop("links", None)

        for field, value in updates.items():
            if field == "status":
                value = ExecutionStatus(value.value)
            setattr(execution, field, value)

        if "artifacts" in payload.model_fields_set:
            execution.artifacts = _build_artifact_models(payload.artifacts or [])

        if "links" in payload.model_fields_set:
            execution.links = _build_external_link_models(payload.links or [])

        current_metadata = snapshot_metadata(execution, audit_fields)
        changes = changed_metadata(previous_metadata, current_metadata)
        if changes:
            now = datetime.now(timezone.utc)
            execution.last_updated_by = user.id
            execution.updated_at = now
            db.add(execution)
            db.add_all(
                [
                    MetadataChange(
                        entity_type="execution",
                        entity_id=execution.id,
                        field_name=field_name,
                        old_value=old_value,
                        new_value=new_value,
                        editor_id=user.id,
                        changed_at=now,
                        reason=payload.edit_reason,
                    )
                    for field_name, old_value, new_value in changes
                ]
            )
            db.flush()
        else:
            db.rollback()

    db.expire_all()
    sim_loaded = (
        _execution_detail_query(db).filter(Execution.id == execution_id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load updated {entity_label}.",
        )

    return sim_loaded


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


def _require_diagnostics_scanner_role(user: User) -> None:
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=403,
            detail="Scanner access requires an administrator or service account.",
        )


def _unsafe_archive_relative_path(value: str) -> bool:
    return value.startswith("/") or any(
        part in {"", ".", ".."} for part in value.split("/")
    )


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


def _get_execution(
    execution_id: UUID,
    db: Session,
    *,
    entity_label: str,
) -> Execution:
    execution = (
        _execution_detail_query(db).filter(Execution.id == execution_id).one_or_none()
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_label.capitalize()} not found",
        )

    return execution


def _case_detail_query(db: Session):
    """Return a case detail query with all data required by its response."""
    return (
        db.query(Case)
        .options(
            selectinload(Case.machine),
            selectinload(Case.executions).selectinload(Execution.artifacts),
        )
        .options(selectinload(Case.links))
    )


def _get_case(case_id: UUID, db: Session) -> Case:
    """Retrieve a case by its immutable internal identifier."""
    case = _case_detail_query(db).filter(Case.id == case_id).one_or_none()

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


def _get_case_by_identity(
    *,
    db: Session,
    machine_name: str,
    hpc_username: str,
    case_name: str,
) -> Case:
    """Retrieve a case by its immutable machine, user, and name identity."""
    machine = resolve_machine_by_name(db, machine_name)

    if machine is None:
        raise HTTPException(status_code=404, detail="Case not found")

    case = (
        _case_detail_query(db)
        .filter(Case.machine_id == machine.id)
        .filter(Case.hpc_username == hpc_username)
        .filter(Case.name == case_name)
        .one_or_none()
    )

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


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

    for execution in case.executions:
        summaries.append(
            ExecutionSummaryOut(
                id=execution.id,
                execution_id=execution.execution_id,
                case_hash=execution.case_hash,
                compute_type=execution.compute_type,
                status=execution.status,
                simulation_start_date=execution.simulation_start_date,
                simulation_end_date=execution.simulation_end_date,
            )
        )

    return {
        "id": case.id,
        "name": case.name,
        "case_group": case.case_group,
        "executions": summaries,
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
        ExecutionSummaryOut
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


def _distinct_query_values(query, column) -> list:
    """Return sorted non-null values from an already constrained query."""
    return [
        value
        for (value,) in query.with_entities(distinct(column))
        .filter(column.is_not(None))
        .order_by(column)
        .all()
    ]


def _filtered_cases_for_facets(db: Session, filters: dict, *, exclude: str):
    """Apply list-case semantics while omitting one facet's own filter."""
    query = db.query(Case)
    if filters["search"] and exclude != "search":
        query = query.filter(Case.name.ilike(f"%{filters['search'].strip()}%"))
    for key, column in (
        ("name", Case.name),
        ("case_group", Case.case_group),
        ("machine_id", Case.machine_id),
        ("hpc_username", Case.hpc_username),
    ):
        if filters[key] is not None and exclude != key:
            query = query.filter(column == filters[key])

    predicates = _case_execution_facet_predicates(filters, exclude=exclude)
    if predicates:
        query = query.filter(Case.executions.any(and_(*predicates)))
    return query


def _filtered_executions_for_facets(db: Session, filters: dict, *, exclude: str):
    """Return executions matching the same-case execution filter semantics."""
    query = db.query(Execution).join(Case)
    if filters["search"] and exclude != "search":
        query = query.filter(Case.name.ilike(f"%{filters['search'].strip()}%"))
    for key, column in (
        ("name", Case.name),
        ("case_group", Case.case_group),
        ("machine_id", Case.machine_id),
        ("hpc_username", Case.hpc_username),
    ):
        if filters[key] is not None and exclude != key:
            query = query.filter(column == filters[key])
    predicates = _case_execution_facet_predicates(filters, exclude=exclude)
    if predicates:
        query = query.filter(*predicates)
    return query


def _case_execution_facet_predicates(filters: dict, *, exclude: str):
    """Build execution predicates shared by case and execution facet queries."""
    predicates: list[ColumnElement[bool]] = []
    if filters["execution_id"] and exclude != "execution_id":
        predicates.append(
            Execution.execution_id.ilike(f"%{filters['execution_id'].strip()}%")
        )
    for key, column in (
        ("status", Execution.status),
        ("simulation_type", Execution.simulation_type),
        ("campaign", Execution.campaign),
        ("initialization_type", Execution.initialization_type),
        ("compiler", Execution.compiler),
        ("git_tag", Execution.git_tag),
        ("created_by", Execution.created_by),
    ):
        if filters[key] is not None and exclude != key:
            predicates.append(column == filters[key])
    return predicates


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


def _machine_filter_options_for_query(query) -> list[FilterOptionOut]:
    """Return machine options represented by a constrained case query."""
    rows = (
        query.join(Machine, Machine.id == Case.machine_id)
        .with_entities(Machine.id, Machine.name)
        .distinct()
        .order_by(Machine.name, Machine.id)
        .all()
    )
    return [
        FilterOptionOut(value=str(machine_id), label=name) for machine_id, name in rows
    ]


def _creator_filter_options(db: Session) -> list[FilterOptionOut]:
    """Return execution creators with stable IDs and email labels."""
    rows = (
        db.query(User.id, User.email)  # ty: ignore[no-matching-overload] -- SQLAlchemy mapped descriptors are not recognized as query columns.
        .join(Execution, Execution.created_by == User.id)
        .distinct()
        .order_by(User.email, User.id)
        .all()
    )
    return [FilterOptionOut(value=str(user_id), label=email) for user_id, email in rows]


def _creator_filter_options_for_query(query) -> list[FilterOptionOut]:
    """Return creator options represented by a constrained execution query."""
    rows = (
        query.join(User, Execution.created_by == User.id)
        .with_entities(User.id, User.email)
        .distinct()
        .order_by(User.email, User.id)
        .all()
    )
    return [FilterOptionOut(value=str(user_id), label=email) for user_id, email in rows]


def _get_metadata_history(
    db: Session,
    *,
    entity_type: EntityType,
    entity_id: UUID,
    page: int,
    page_size: int,
) -> MetadataHistoryPageOut:
    event_query = (
        db.query(
            MetadataChange.changed_at,
            MetadataChange.editor_id,
            MetadataChange.reason,
            func.max(MetadataChange.id.cast(String)).label("sort_id"),
        )
        .filter(
            MetadataChange.entity_type == entity_type,
            MetadataChange.entity_id == entity_id,
        )
        .group_by(
            MetadataChange.changed_at,
            MetadataChange.editor_id,
            MetadataChange.reason,
        )
    )
    total = db.query(func.count()).select_from(event_query.subquery()).scalar() or 0
    events = (
        event_query.order_by(
            desc(MetadataChange.changed_at),
            desc("sort_id"),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    if not events:
        return MetadataHistoryPageOut(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
        )

    event_filters = [
        and_(
            MetadataChange.changed_at == event.changed_at,
            MetadataChange.editor_id == event.editor_id,
            MetadataChange.reason.is_not_distinct_from(event.reason),
        )
        for event in events
    ]
    items = (
        db.query(MetadataChange)
        .options(joinedload(MetadataChange.editor))
        .filter(
            MetadataChange.entity_type == entity_type,
            MetadataChange.entity_id == entity_id,
            or_(*event_filters),
        )
        .order_by(desc(MetadataChange.changed_at), desc(MetadataChange.id))
        .all()
    )
    return MetadataHistoryPageOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _case_to_detail_out(case: Case) -> CaseDetailOut:
    """Convert a Case ORM instance to CaseDetailOut."""
    result = CaseDetailOut(
        **_build_case_summary(case),
        artifacts=_case_execution_artifacts(case),
        description=case.description,
        key_features=case.key_features,
        known_issues=case.known_issues,
        notes_markdown=case.notes_markdown,
    )

    return result


def _case_execution_artifacts(case: Case) -> list[CaseExecutionArtifactOut]:
    """Serialize execution-owned artifacts while retaining their execution identity."""
    artifacts: list[CaseExecutionArtifactOut] = []

    for execution in sorted(
        case.executions,
        key=lambda execution: (execution.execution_id, str(execution.id)),
    ):
        for artifact in sorted(
            execution.artifacts,
            key=lambda artifact: (
                artifact.kind.value,
                artifact.created_at,
                str(artifact.id),
            ),
        ):
            artifacts.append(
                CaseExecutionArtifactOut(
                    id=artifact.id,
                    kind=ArtifactKind(artifact.kind),
                    uri=artifact.uri,
                    label=artifact.label,
                    created_at=artifact.created_at,
                    updated_at=artifact.updated_at,
                    execution_uuid=execution.id,
                    execution_id=execution.execution_id,
                )
            )

    return artifacts


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
    owner_type = "execution" if link.execution_id is not None else "case"

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


def _execution_to_out(execution: Execution) -> ExecutionOut:
    """Convert an Execution ORM instance to the canonical response schema."""
    case = execution.case
    llm_available = is_summary_llm_available()
    merged_links = merge_execution_and_case_links(execution.links, case.links)
    serialized_links = [
        ExecutionExternalLinkOut.model_validate(
            {
                **_external_link_to_out(link),
                "owner_type": (
                    "execution" if link.execution_id is not None else "case"
                ),
            }
        )
        for link in merged_links
    ]

    return ExecutionOut.model_validate(
        {
            **{
                key: value
                for key, value in execution.__dict__.items()
                if not key.startswith("_")
            },
            "case_name": case.name,
            "case_group": case.case_group,
            "machine_id": case.machine_id,
            "hpc_username": case.hpc_username,
            "machine": case.machine,
            "links": serialized_links,
            "summary_capabilities": ExecutionSummaryCapabilitiesOut(
                llm_available=llm_available,
                auto_generate_deterministic_on_load=not llm_available,
            ),
        },
        from_attributes=True,
    )
