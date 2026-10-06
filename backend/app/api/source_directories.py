"""Trusted scanner submissions for original performance directories."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.schemas import (
    SourceDirectoriesRequest,
    SourceDirectoriesResponse,
)
from app.features.ingestion.source_directories import persist_observed_directories
from app.features.machine.utils import resolve_machine_by_name
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])


@router.post("/source-directories", response_model=SourceDirectoriesResponse)
def record_source_directories(
    payload: SourceDirectoriesRequest,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> SourceDirectoriesResponse:
    """Record directories without uploading or changing ingestion checkpoints."""
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=403,
            detail="Only administrators and service accounts may record source directories.",
        )
    machine = resolve_machine_by_name(db, payload.machine_name)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found.")

    try:
        with transaction(db):
            persist_observed_directories(db, machine.id, payload.directories)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return SourceDirectoriesResponse(recorded_count=len(payload.directories))
