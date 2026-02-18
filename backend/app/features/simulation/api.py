from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.simulation.models import Artifact, ExternalLink, Simulation
from app.features.simulation.schemas import SimulationCreate, SimulationOut
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/simulations", tags=["Simulations"])


@router.post(
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

    return SimulationOut.model_validate(sim, from_attributes=True)


@router.get(
    "",
    response_model=list[SimulationOut],
    responses={
        200: {"description": "List all simulations."},
        401: {"description": "Unauthorized."},
        500: {"description": "Internal server error."},
    },
)
def list_simulations(db: Session = Depends(get_database_session)):
    """
    Retrieve a list of simulations from the database, ordered by creation date
    in descending order.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default obtained via
        `Depends(get_database_session)`.

    Returns
    -------
    list
        A list of `Simulation` objects, ordered by their `created_at` timestamp
        in descending order.
    """
    sims = (
        db.query(Simulation)
        .options(
            joinedload(Simulation.machine),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .order_by(Simulation.created_at.desc())
        .all()
    )
    return sims


@router.get(
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
            joinedload(Simulation.machine),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .filter(Simulation.id == sim_id)
        .first()
    )

    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    return sim
