from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.machine.models import Machine
from app.features.machine.schemas import MachineCreate, MachineOut

router = APIRouter(prefix="/machines", tags=["Machines"])


@router.post("", response_model=MachineOut, status_code=status.HTTP_201_CREATED)
def create_machine(payload: MachineCreate, db: Session = Depends(get_database_session)):
    """Create a new machine.

    This endpoint allows the creation of a new machine in the database.
    It ensures that the machine name is unique and returns the created machine
    object upon success.

    Parameters
    ----------
    payload : MachineCreate
        The data required to create a new machine, including its attributes.
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_database_session)`.

    Returns
    -------
    MachineOut
        The newly created machine object.

    Raises
    ------
    HTTPException
        If a machine with the same name already exists, an HTTP 400 Bad Request
        error is raised with an appropriate message.
    """
    if db.query(Machine).filter(Machine.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Machine with this name already exists",
        )

    new_machine = Machine(**payload.model_dump())

    with transaction(db):
        db.add(new_machine)
        db.flush()

    return new_machine


@router.get("", response_model=list[MachineOut])
def list_machines(db: Session = Depends(get_database_session)):
    """
    Retrieve a list of machines from the database, ordered by name in ascending
    order.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_database_session)`.

    Returns
    -------
    list
        A list of `Machine` objects retrieved from the database.
    """
    machines = db.query(Machine).order_by(Machine.name.asc()).all()

    return machines


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: UUID, db: Session = Depends(get_database_session)):
    """Retrieve a machine by its ID.

    Parameters
    ----------
    machine_id : UUID
        The unique identifier of the machine to retrieve.
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_database_session)`.

    Returns
    -------
    MachineOut
        The machine data serialized as a `MachineOut` model.

    Raises
    ------
    HTTPException
        If the machine with the given ID is not found, raises a 404 HTTP exception
        with the message "Machine not found".
    """
    machine = db.query(Machine).filter(Machine.id == machine_id).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    return machine
