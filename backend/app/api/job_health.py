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
    register_reporting_job,
    summarize_job_health,
    to_job_read,
)
from app.features.ingestion.models import ScheduledJob
from app.features.ingestion.schemas import (
    SCHEDULED_JOB_ID_PATTERN,
    ScheduledJobHealthResponse,
    ScheduledJobRead,
    ScheduledJobRegister,
    ScheduledJobReport,
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
    """Create or update a job's reporting account and health thresholds.

    Optional: jobs register themselves on their first report. Pre-register a job
    to assign its account or thresholds, or to report it stale before it runs.
    """
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
    """Record a run start, registering an unknown job. Retries are idempotent."""
    try:
        with transaction(db):
            job = _get_reporting_job(db, job_id, user, payload)
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
    try:
        with transaction(db):
            job = _get_reporting_job(db, job_id, user, payload)
            run = record_run_finish(db, job, run_id, payload, _now())
    except JobRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ScheduledJobRunRead.model_validate(run)


def _get_reporting_job(
    db: Session, job_id: str, user: User, report: ScheduledJobReport
) -> ScheduledJob:
    """Return the reported job, registering it on its first report.

    Call inside the run's transaction so a new job is committed with its run.
    """
    # Check the role first so other callers cannot probe which job IDs exist.
    if user.role != UserRole.SERVICE_ACCOUNT:
        raise HTTPException(
            status_code=403, detail="Only service accounts may report job runs."
        )
    machine = _resolve_request_machine(db, report.machine_name)
    job = db.get(ScheduledJob, job_id)
    if job is None:
        return register_reporting_job(db, job_id, report.scan_mode, machine, user)
    if job.service_account_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the job's service account may report its runs.",
        )
    # Distinct jobs must not share an ID.
    if (job.machine_id, job.scan_mode) != (machine.id, report.scan_mode):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Job '{job_id}' is registered for {job.machine.name} "
                f"{job.scan_mode} runs."
            ),
        )

    return job


def _now() -> datetime:
    return datetime.now(timezone.utc)
