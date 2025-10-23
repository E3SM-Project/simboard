from uuid import UUID

from app.db.models.machine import Machine
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas import MachineCreate, MachineOut

router = APIRouter(prefix="/machines", tags=["Machines"])


@router.post("", response_model=MachineOut, status_code=status.HTTP_201_CREATED)
async def create_machine(
    payload: MachineCreate, db: AsyncSession = Depends(get_async_session)
):
    """Create a new machine.

    This endpoint allows the creation of a new machine in the database.
    It ensures that the machine name is unique and returns the created machine
    object upon success.

    Parameters
    ----------
    payload : MachineCreate
        The data required to create a new machine, including its attributes.
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_db)`.

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
    result = await db.execute(select(Machine).filter(Machine.name == payload.name))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Machine with this name already exists",
        )

    # ✅ Create and persist new machine
    new_machine = Machine(**payload.model_dump())

    db.add(new_machine)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(new_machine)
    return new_machine


@router.get("", response_model=list[MachineOut])
async def list_machines(db: AsyncSession = Depends(get_async_session)):
    """
    Retrieve a list of machines from the database, ordered by name in ascending
    order.

    Parameters
    ----------
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_db)`.

    Returns
    -------
    list
        A list of `Machine` objects retrieved from the database.
    """
    result = await db.execute(select(Machine).order_by(Machine.name.asc()))
    machines = result.scalars().all()

    return machines


@router.get("/{machine_id}", response_model=MachineOut)
async def get_machine(machine_id: UUID, db: AsyncSession = Depends(get_async_session)):
    """Retrieve a machine by its ID.

    Parameters
    ----------
    machine_id : UUID
        The unique identifier of the machine to retrieve.
    db : Session, optional
        The database session dependency, by default provided by `Depends(get_db)`.

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
    result = await db.execute(select(Machine).filter(Machine.id == machine_id))
    machine = result.scalars().first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    return machine
