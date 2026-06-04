from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload, selectinload

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.assistant.orchestrator import is_summary_llm_available
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.enums import ExternalLinkKind
from app.features.simulation.link_utils import merge_simulation_and_case_links
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation
from app.features.simulation.schemas import (
    CaseOut,
    DiagnosticsLinkRequest,
    SimulationCreate,
    SimulationOut,
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
    response_model=list[CaseOut],
    responses={
        200: {"description": "List all cases."},
        500: {"description": "Internal server error."},
    },
)
def list_cases(db: Session = Depends(get_database_session)) -> list[CaseOut]:
    """Retrieve all cases with nested simulation summaries.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default provided by
        `Depends(get_database_session)`.

    Returns
    -------
    list[CaseOut]
        A list of cases, each with nested summaries of their associated
        simulations.
    """
    cases = (
        db.query(Case)
        .options(selectinload(Case.machine), selectinload(Case.simulations))
        .order_by(Case.created_at.desc())
        .all()
    )

    resp = [_case_to_out(c) for c in cases]

    return resp


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
    response_model=CaseOut,
    responses={
        200: {"description": "Case found."},
        404: {"description": "Case not found."},
        500: {"description": "Internal server error."},
    },
)
def get_case(case_id: UUID, db: Session = Depends(get_database_session)) -> CaseOut:
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
    CaseOut
        The case object with nested simulation summaries if found.
    """
    case = (
        db.query(Case)
        .options(selectinload(Case.machine), selectinload(Case.simulations))
        .options(selectinload(Case.links))
        .filter(Case.id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    resp = _case_to_out(case, include_links=True)

    return resp


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

    sim = Simulation(
        **payload.model_dump(
            by_alias=False,
            exclude={"artifacts", "links"},
            exclude_unset=True,
        ),
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
        _simulation_detail_query(db).filter(Simulation.id == sim.id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load newly created simulation.",
        )

    result = _simulation_to_out(sim_loaded)

    return result


@diagnostics_router.post(
    "/link",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Diagnostics linked successfully."},
        401: {"description": "Unauthorized."},
        403: {"description": "Forbidden."},
        404: {"description": "Matching case not found."},
        409: {"description": "Ambiguous case match."},
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
    response_model=list[SimulationOut],
    responses={
        200: {"description": "List all simulations."},
        401: {"description": "Unauthorized."},
        500: {"description": "Internal server error."},
    },
)
def list_simulations(
    db: Session = Depends(get_database_session),
    case_name: str | None = Query(
        None,
        description="Filter simulations by exact case name.",
    ),
    case_group: str | None = Query(
        None,
        description="Filter simulations by exact case group.",
    ),
):
    """
    Retrieve a list of simulations from the database, ordered by creation date
    in descending order.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default obtained via
        `Depends(get_database_session)`.
    case_name : str, optional
        If provided, only simulations whose associated case name matches
        exactly will be returned.
    case_group : str, optional
        If provided, only simulations whose associated case group matches
        exactly will be returned.

    Returns
    -------
    list
        A list of `Simulation` objects, ordered by their `created_at` timestamp
        in descending order.
    """
    query = db.query(Simulation).options(
        joinedload(Simulation.case).joinedload(Case.machine),
        joinedload(Simulation.case).selectinload(Case.links),
        selectinload(Simulation.artifacts),
        selectinload(Simulation.links),
    )

    if case_name is not None:
        query = query.filter(Simulation.case.has(name=case_name))
    if case_group is not None:
        query = query.filter(Simulation.case.has(case_group=case_group))

    sims = query.order_by(Simulation.created_at.desc()).all()
    return [_simulation_to_out(s) for s in sims]


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

    sim = db.query(Simulation).filter(Simulation.id == sim_id).one_or_none()

    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    now = datetime.now(timezone.utc)
    updates = payload.model_dump(by_alias=False, exclude_unset=True)
    updates.pop("artifacts", None)
    updates.pop("links", None)

    for field, value in updates.items():
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
        _simulation_detail_query(db).filter(Simulation.id == sim_id).one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load updated simulation.",
        )

    return _simulation_to_out(sim_loaded)


def _resolve_case_id_for_diagnostics_link(
    *,
    db: Session,
    case_name: str,
    machine_name: str,
    hpc_username: str,
) -> UUID:
    """Resolve a unique case ID from case, machine, and HPC username."""
    matches = (
        db.query(Case.id)
        .join(Simulation, Simulation.case_id == Case.id)
        .join(Machine, Simulation.machine_id == Machine.id)
        .filter(Case.name == case_name)
        .filter(Machine.name == machine_name)
        .filter(Simulation.hpc_username == hpc_username)
        .distinct()
        .all()
    )

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No case matched the provided case_name, machine, and hpc_username.",
        )

    # TODO(#193): This ambiguity branch is not reachable while Case.name remains
    # globally unique. If case identity moves to (case_name, machine, hpc_username),
    # keep this 409 path and replace patched coverage with a DB-backed test.
    # https://github.com/E3SM-Project/simboard/issues/193
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Multiple cases matched the provided case_name, machine, and hpc_username.",
        )

    return matches[0][0]


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
    sim = _simulation_detail_query(db).filter(Simulation.id == sim_id).one_or_none()

    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    return _simulation_to_out(sim)


def _case_to_out(case: Case, *, include_links: bool = False) -> CaseOut:
    """Convert a Case ORM instance to CaseOut with nested SimulationSummaryOut.

    Parameters
    ----------
    case : Case
        The Case ORM instance to convert.

    Returns
    -------
    CaseOut
        The corresponding CaseOut schema instance with nested
        SimulationSummaryOut
    """
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

    for sim in case.simulations:
        summaries.append(
            SimulationSummaryOut(
                id=sim.id,
                execution_id=sim.execution_id,
                case_hash=sim.case_hash,
                status=sim.status,
                simulation_start_date=sim.simulation_start_date,
                simulation_end_date=sim.simulation_end_date,
            )
        )

    result = CaseOut(
        id=case.id,
        name=case.name,
        case_group=case.case_group,
        simulations=summaries,
        machine_names=machine_names,
        hpc_usernames=hpc_usernames,
        links=case.links if include_links else [],
        created_at=case.created_at,
        updated_at=case.updated_at,
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


def _simulation_detail_query(db: Session):
    return db.query(Simulation).options(
        joinedload(Simulation.case).joinedload(Case.machine),
        joinedload(Simulation.case).selectinload(Case.links),
        joinedload(Simulation.machine),
        selectinload(Simulation.artifacts),
        selectinload(Simulation.links),
    )


def _simulation_to_out(sim: Simulation) -> SimulationOut:
    """Convert a Simulation ORM instance to a SimulationOut schema.

    Derives ``case_name`` and ``case_group`` from the associated Case relationship.

    Parameters
    ----------
    sim : Simulation
        The Simulation ORM instance to convert.

    Returns
    -------
    SimulationOut
        The corresponding SimulationOut schema instance with additional derived
        fields.
    """
    case = sim.case
    llm_available = is_summary_llm_available()
    merged_links = merge_simulation_and_case_links(sim.links, case.links)

    result = SimulationOut.model_validate(
        {
            **{k: v for k, v in sim.__dict__.items() if not k.startswith("_")},
            "case_name": case.name,
            "case_group": case.case_group,
            "machine_id": case.machine_id,
            "hpc_username": case.hpc_username,
            "machine": case.machine,
            "links": merged_links,
            "summary_capabilities": SimulationSummaryCapabilitiesOut(
                llm_available=llm_available,
                auto_generate_deterministic_on_load=not llm_available,
            ),
        },
        from_attributes=True,
    )

    return result
