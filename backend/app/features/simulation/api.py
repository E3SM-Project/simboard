from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation
from app.features.simulation.schemas import (
    CaseOut,
    SimulationCreate,
    SimulationOut,
    SimulationSummaryOut,
)
from app.features.user.manager import current_active_user
from app.features.user.models import User

simulation_router = APIRouter(prefix="/simulations", tags=["Simulations"])
case_router = APIRouter(prefix="/cases", tags=["Cases"])


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
        .options(selectinload(Case.simulations).selectinload(Simulation.machine))
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
    names = db.query(Case.name).order_by(Case.name).all()

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
        .options(selectinload(Case.simulations).selectinload(Simulation.machine))
        .filter(Case.id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    resp = _case_to_out(case)

    return resp


def _case_to_out(case: Case) -> CaseOut:
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
        {
            sim.machine.name
            for sim in case.simulations
            if sim.machine is not None and sim.machine.name
        },
        key=lambda name: name.lower(),
    )
    hpc_usernames = sorted(
        {sim.hpc_username for sim in case.simulations if sim.hpc_username},
        key=lambda username: username.lower(),
    )

    for sim in case.simulations:
        is_canonical = sim.id == case.canonical_simulation_id
        change_count = len(sim.run_config_deltas) if sim.run_config_deltas else 0

        summaries.append(
            SimulationSummaryOut(
                id=sim.id,
                execution_id=sim.execution_id,
                status=sim.status,
                is_canonical=is_canonical,
                change_count=change_count,
                simulation_start_date=sim.simulation_start_date,
                simulation_end_date=sim.simulation_end_date,
            )
        )

    result = CaseOut(
        id=case.id,
        name=case.name,
        case_group=case.case_group,
        canonical_simulation_id=case.canonical_simulation_id,
        simulations=summaries,
        machine_names=machine_names,
        hpc_usernames=hpc_usernames,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )

    return result


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
        machine_id=payload.machine_id,
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
        for artifact in payload.artifacts:
            artifact_data = artifact.model_dump(by_alias=False, exclude_unset=True)
            artifact_data["uri"] = str(artifact.uri)
            sim.artifacts.append(Artifact(**artifact_data))

    if payload.links:
        for link in payload.links:
            link_data = link.model_dump(by_alias=False, exclude_unset=True)
            link_data["url"] = str(link.url)
            sim.links.append(ExternalLink(**link_data))

    with transaction(db):
        db.add(sim)
        db.flush()

        if case.canonical_simulation_id is None:
            sim.run_config_deltas = None
            case.canonical_simulation_id = sim.id
            db.add(case)

    # Re-query with relationships loaded
    sim_loaded = (
        db.query(Simulation)
        .options(
            joinedload(Simulation.case),
            joinedload(Simulation.machine),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .filter(Simulation.id == sim.id)
        .one_or_none()
    )

    if sim_loaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load newly created simulation.",
        )

    result = _simulation_to_out(sim_loaded)

    return result


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
        joinedload(Simulation.case),
        joinedload(Simulation.machine),
        selectinload(Simulation.artifacts),
        selectinload(Simulation.links),
    )

    if case_name is not None:
        query = query.filter(Simulation.case.has(name=case_name))
    if case_group is not None:
        query = query.filter(Simulation.case.has(case_group=case_group))

    sims = query.order_by(Simulation.created_at.desc()).all()
    return [_simulation_to_out(s) for s in sims]


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
    sim = (
        db.query(Simulation)
        .options(
            joinedload(Simulation.case),
            joinedload(Simulation.machine),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .filter(Simulation.id == sim_id)
        .one_or_none()
    )

    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    return _simulation_to_out(sim)


def _simulation_to_out(sim: Simulation) -> SimulationOut:
    """Convert a Simulation ORM instance to a SimulationOut schema.

    Derives ``case_name``, ``is_canonical``, and ``change_count`` from
    the associated Case relationship.

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
    is_canonical = sim.id == case.canonical_simulation_id
    change_count = len(sim.run_config_deltas) if sim.run_config_deltas else 0

    result = SimulationOut.model_validate(
        {
            **{k: v for k, v in sim.__dict__.items() if not k.startswith("_")},
            "case_name": case.name,
            "case_group": case.case_group,
            "is_canonical": is_canonical,
            "change_count": change_count,
        },
        from_attributes=True,
    )

    return result
