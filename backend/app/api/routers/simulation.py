from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_db, transaction
from app.db.artifact import Artifact
from app.db.link import ExternalLink
from app.db.simulation import Simulation
from app.schemas import SimulationCreate, SimulationOut

router = APIRouter(prefix="/simulations", tags=["Simulations"])


@router.post("", response_model=SimulationOut, status_code=status.HTTP_201_CREATED)
def create_simulation(payload: SimulationCreate, db: Session = Depends(get_db)):
    """Create a new simulation record in the database.

    Parameters
    ----------
    payload : SimulationCreate
        The data required to create a new simulation, including optional artifacts
        and links.
    db : Session, optional
        The database session dependency, by default obtained via `Depends(get_db)`.

    Returns
    -------
    SimulationOut
        The created simulation object validated and serialized as `SimulationOut`.
    """
    sim = Simulation(
        **payload.model_dump(
            by_alias=False,
            exclude={"artifacts", "links"},
            exclude_unset=True,
        )
    )

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

    # Start a database transaction to ensure atomicity of the operation
    with transaction(db):
        # Add the simulation object to the database session.
        db.add(sim)
        # Flush the session to persist the simulation object and generate its ID
        db.flush()

    return SimulationOut.model_validate(sim, from_attributes=True)


@router.get("", response_model=list[SimulationOut])
def list_simulations(db: Session = Depends(get_db)):
    """
    Retrieve a list of simulations from the database, ordered by creation date
    in descending order.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default obtained via `Depends(get_db)`.

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


@router.get("/{sim_id}", response_model=SimulationOut)
def get_simulation(sim_id: UUID, db: Session = Depends(get_db)):
    """Retrieve a simulation by its unique identifier.

    Parameters
    ----------
    sim_id : UUID
        The unique identifier of the simulation to retrieve.
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_db)`.

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
