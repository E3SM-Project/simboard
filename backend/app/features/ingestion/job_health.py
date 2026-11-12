"""Scheduled job registration, run reporting, and derived health."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.features.ingestion.enums import ScheduledJobHealth, ScheduledJobRunStatus
from app.features.ingestion.models import ScheduledJob, ScheduledJobRun
from app.features.ingestion.schemas import (
    ScheduledJobHealthRead,
    ScheduledJobRead,
    ScheduledJobRegister,
    ScheduledJobRunFinish,
    ScheduledJobRunRead,
    ScheduledJobRunStart,
)
from app.features.machine.models import Machine
from app.features.user.models import User

RUN_RETENTION = timedelta(days=90)


class JobRunConflictError(Exception):
    """A report conflicts with another job's run or a recorded outcome."""


def register_job(
    db: Session,
    job_id: str,
    payload: ScheduledJobRegister,
    machine: Machine,
    service_account: User,
) -> ScheduledJob:
    """Create or update one job's identity, reporting account, and thresholds."""
    job = db.get(ScheduledJob, job_id) or ScheduledJob(id=job_id)
    job.machine = machine
    job.scan_mode = payload.scan_mode
    job.service_account_id = service_account.id
    job.max_silence_minutes = payload.max_silence_minutes
    job.max_duration_minutes = payload.max_duration_minutes
    db.add(job)

    return job


def record_run_start(
    db: Session,
    job: ScheduledJob,
    run_id: UUID,
    payload: ScheduledJobRunStart,
    now: datetime,
) -> ScheduledJobRun:
    """Record a run start; repeated starts and starts after finish are no-ops."""
    run = _get_job_run(db, job, run_id)
    if run is None:
        run = ScheduledJobRun(
            id=run_id,
            job_id=job.id,
            status=ScheduledJobRunStatus.RUNNING,
            started_at=payload.started_at,
            reported_at=now,
        )
        db.add(run)
        db.execute(
            delete(ScheduledJobRun).where(
                ScheduledJobRun.job_id == job.id,
                ScheduledJobRun.reported_at < now - RUN_RETENTION,
            )
        )

    return run


def record_run_finish(
    db: Session,
    job: ScheduledJob,
    run_id: UUID,
    payload: ScheduledJobRunFinish,
    now: datetime,
) -> ScheduledJobRun:
    """Record a run outcome, creating the run if its start report was lost."""
    run = _get_job_run(db, job, run_id)
    if run is None:
        run = ScheduledJobRun(
            id=run_id, job_id=job.id, started_at=payload.started_at, reported_at=now
        )
        db.add(run)
    elif run.status != ScheduledJobRunStatus.RUNNING:
        if _finish_values(payload) != _recorded_finish_values(run):
            raise JobRunConflictError(f"Run {run_id} already has a different outcome.")

        return run

    failure = payload.failure
    run.status = (
        ScheduledJobRunStatus.SUCCEEDED
        if payload.exit_code == 0
        else ScheduledJobRunStatus.FAILED
    )
    run.finished_at = payload.finished_at
    run.finish_reported_at = now
    run.exit_code = payload.exit_code
    run.failure_reason = failure.reason if failure else None
    run.failure_message = failure.message if failure else None
    run.failure_status_code = failure.status_code if failure else None
    run.failure_transient = failure.transient if failure else None

    return run


def summarize_job_health(
    db: Session, now: datetime, machine_id: UUID | None = None
) -> list[ScheduledJobHealthRead]:
    """Derive health for every registered job from server-observed report times."""
    query = (
        select(ScheduledJob)
        .options(joinedload(ScheduledJob.machine))
        .order_by(ScheduledJob.id)
    )
    if machine_id is not None:
        query = query.where(ScheduledJob.machine_id == machine_id)

    return [_job_health(db, job, now) for job in db.scalars(query)]


def to_job_read(job: ScheduledJob) -> ScheduledJobRead:
    return ScheduledJobRead(
        id=job.id,
        machine_name=job.machine.name,
        scan_mode=job.scan_mode,
        max_silence_minutes=job.max_silence_minutes,
        max_duration_minutes=job.max_duration_minutes,
    )


def _get_job_run(
    db: Session, job: ScheduledJob, run_id: UUID
) -> ScheduledJobRun | None:
    run = db.get(ScheduledJobRun, run_id)
    if run is not None and run.job_id != job.id:
        raise JobRunConflictError(f"Run {run_id} belongs to another job.")

    return run


def _finish_values(payload: ScheduledJobRunFinish) -> tuple:
    failure = payload.failure

    return (
        payload.finished_at,
        payload.exit_code,
        failure.reason if failure else None,
        failure.message if failure else None,
        failure.status_code if failure else None,
        failure.transient if failure else None,
    )


def _recorded_finish_values(run: ScheduledJobRun) -> tuple:
    return (
        run.finished_at,
        run.exit_code,
        run.failure_reason,
        run.failure_message,
        run.failure_status_code,
        run.failure_transient,
    )


def _job_health(
    db: Session, job: ScheduledJob, now: datetime
) -> ScheduledJobHealthRead:
    runs = select(ScheduledJobRun).where(ScheduledJobRun.job_id == job.id)
    running = runs.where(ScheduledJobRun.status == ScheduledJobRunStatus.RUNNING)
    active = running.where(
        ScheduledJobRun.reported_at >= now - timedelta(minutes=job.max_duration_minutes)
    )
    newest_run = db.scalars(
        runs.order_by(ScheduledJobRun.reported_at.desc()).limit(1)
    ).first()
    latest_completed = db.scalars(
        runs.where(ScheduledJobRun.status != ScheduledJobRunStatus.RUNNING)
        .order_by(ScheduledJobRun.finish_reported_at.desc())
        .limit(1)
    ).first()
    active_run = db.scalars(
        active.order_by(ScheduledJobRun.reported_at.desc()).limit(1)
    ).first()
    active_run_count = db.scalar(select(func.count()).select_from(active.subquery()))
    report_times = [newest_run.reported_at] if newest_run else []
    if latest_completed and latest_completed.finish_reported_at:
        report_times.append(latest_completed.finish_reported_at)
    last_reported_at = max(report_times, default=None)

    return ScheduledJobHealthRead(
        **to_job_read(job).model_dump(),
        health=_derive_health(
            job, now, last_reported_at, newest_run, latest_completed, active_run
        ),
        last_reported_at=last_reported_at,
        latest_completed_run=_to_run_read(latest_completed),
        active_run=_to_run_read(active_run),
        active_run_count=active_run_count or 0,
    )


def _derive_health(
    job: ScheduledJob,
    now: datetime,
    last_reported_at: datetime | None,
    newest_run: ScheduledJobRun | None,
    latest_completed: ScheduledJobRun | None,
    active_run: ScheduledJobRun | None,
) -> ScheduledJobHealth:
    if last_reported_at is None:
        return ScheduledJobHealth.STALE
    # A run within its allowed duration may outlast the silence interval.
    silence_limit = timedelta(minutes=job.max_silence_minutes)
    if active_run is None and now - last_reported_at > silence_limit:
        return ScheduledJobHealth.STALE
    if latest_completed and latest_completed.status == ScheduledJobRunStatus.FAILED:
        return ScheduledJobHealth.FAILED
    if active_run is not None:
        return ScheduledJobHealth.RUNNING
    # The newest run started but exceeded its allowed duration without finishing.
    # Missing completion is not proof of failure.
    if newest_run is not None and newest_run.status == ScheduledJobRunStatus.RUNNING:
        return ScheduledJobHealth.STALE

    return ScheduledJobHealth.HEALTHY


def _to_run_read(run: ScheduledJobRun | None) -> ScheduledJobRunRead | None:
    return ScheduledJobRunRead.model_validate(run) if run is not None else None
