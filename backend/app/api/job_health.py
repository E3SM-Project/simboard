"""Protected scheduled job registration, run reporting, and health."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.api import (
    _require_ingestion_state_access,
    _resolve_request_machine,
)
from app.features.ingestion.job_health import (
    JobRunConflictError,
    record_run_finish,
    record_run_start,
    register_job,
    summarize_job_health,
    to_job_read,
)
from app.features.ingestion.models import ScheduledJob
from app.features.ingestion.schemas import (
    SCHEDULED_JOB_ID_PATTERN,
    ScheduledJobHealthResponse,
    ScheduledJobRead,
    ScheduledJobRegister,
    ScheduledJobRunFinish,
    ScheduledJobRunRead,
    ScheduledJobRunStart,
)
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole

router = APIRouter(prefix="/ingestions/jobs", tags=["Ingestions"])

JobId = Annotated[str, Path(pattern=SCHEDULED_JOB_ID_PATTERN)]


@router.get("", response_model=ScheduledJobHealthResponse)
def get_scheduled_job_health(
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
    machine_name: str | None = None,
) -> ScheduledJobHealthResponse:
    """Return latest activity and derived health for registered jobs."""
    _require_ingestion_state_access(user, action="read job health")
    machine_id = (
        _resolve_request_machine(db, machine_name).id
        if machine_name is not None
        else None
    )

    return ScheduledJobHealthResponse(jobs=summarize_job_health(db, _now(), machine_id))


@router.put("/{job_id}", response_model=ScheduledJobRead)
def register_scheduled_job(
    job_id: JobId,
    payload: ScheduledJobRegister,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> ScheduledJobRead:
    """Create or update a job's reporting account and health thresholds."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only administrators may register jobs."
        )

    machine = _resolve_request_machine(db, payload.machine_name)
    service_account = (
        db.query(User).filter_by(email=payload.service_account_email).first()
    )
    if service_account is None or service_account.role != UserRole.SERVICE_ACCOUNT:
        raise HTTPException(status_code=404, detail="Service account not found.")

    with transaction(db):
        job = register_job(db, job_id, payload, machine, service_account)

    return to_job_read(job)


@router.put("/{job_id}/runs/{run_id}/start", response_model=ScheduledJobRunRead)
def report_scheduled_job_start(
    job_id: JobId,
    run_id: UUID,
    payload: ScheduledJobRunStart,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> ScheduledJobRunRead:
    """Record a run start. Repeated reports are idempotent."""
    job = _get_reporting_job(db, job_id, user)
    try:
        with transaction(db):
            run = record_run_start(db, job, run_id, payload, _now())
    except JobRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ScheduledJobRunRead.model_validate(run)


@router.put("/{job_id}/runs/{run_id}/finish", response_model=ScheduledJobRunRead)
def report_scheduled_job_finish(
    job_id: JobId,
    run_id: UUID,
    payload: ScheduledJobRunFinish,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> ScheduledJobRunRead:
    """Record a run outcome. Identical retries succeed; changed outcomes conflict."""
    job = _get_reporting_job(db, job_id, user)
    try:
        with transaction(db):
            run = record_run_finish(db, job, run_id, payload, _now())
    except JobRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ScheduledJobRunRead.model_validate(run)


def _get_reporting_job(db: Session, job_id: str, user: User) -> ScheduledJob:
    # Check the role first so other callers cannot probe which job IDs exist.
    if user.role != UserRole.SERVICE_ACCOUNT:
        raise HTTPException(
            status_code=403, detail="Only service accounts may report job runs."
        )
    job = db.get(ScheduledJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.service_account_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the job's service account may report its runs.",
        )

    return job


def _now() -> datetime:
    return datetime.now(timezone.utc)
