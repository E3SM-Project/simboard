"""Trusted metadata-only selection and updates for historical records."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.catalog.models import Case, Execution
from app.features.ingestion.api import _require_ingestion_state_access
from app.features.ingestion.metadata_backfill import (
    MetadataUpdate,
    stored_values,
    update_metadata,
)
from app.features.machine.utils import resolve_machine_by_name
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions/metadata-backfill", tags=["Ingestions"])


def _existing_executions(db: Session, machine_name: str):
    machine = resolve_machine_by_name(db, machine_name)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found.")

    return db.query(Execution).join(Case).filter(Case.machine_id == machine.id)


@router.get("")
def list_records(
    machine_name: str,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
    case_name: str | None = None,
    hpc_username: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    _require_ingestion_state_access(user)
    query = _existing_executions(db, machine_name)

    if case_name:
        query = query.filter(Case.name == case_name)
    if hpc_username:
        query = query.filter(Case.hpc_username == hpc_username)

    rows = (
        query.options(
            selectinload(Execution.source_directories),
            selectinload(Execution.artifacts),
            selectinload(Execution.case),
        )
        .order_by(Execution.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    records = []
    for row in rows:
        try:
            values = stored_values(row).model_dump(mode="json")
            error = None
        except ValueError as exc:
            values = None
            error = str(exc)

        records.append(
            {
                "record_id": str(row.id),
                "case_name": row.case.name,
                "hpc_username": row.case.hpc_username,
                "execution_id": row.execution_id,
                "directories": [
                    {"kind": d.kind, "path": d.path} for d in row.source_directories
                ],
                "values": values,
                "error": error,
            }
        )

    return {"records": records}


@router.post("")
def backfill_record(
    payload: MetadataUpdate,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict:
    _require_ingestion_state_access(user)

    with transaction(db):
        row = (
            _existing_executions(db, payload.machine_name)
            .filter(
                Execution.id == payload.record_id,
                Case.name == payload.case_name,
                Case.hpc_username == payload.hpc_username,
                Execution.execution_id == payload.execution_id,
            )
            .populate_existing()
            .with_for_update(of=Execution)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Matching execution not found.")

        try:
            return update_metadata(db, row, payload, user.id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
