"""Deterministic scheduled job health derivation with fixed timestamps."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.features.ingestion.enums import ScheduledJobRunStatus
from app.features.ingestion.job_health import summarize_job_health
from app.features.ingestion.models import ScheduledJob, ScheduledJobRun
from app.features.machine.models import Machine
from app.features.user.models import User, UserRole

NOW = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
RUNNING = ScheduledJobRunStatus.RUNNING
SUCCEEDED = ScheduledJobRunStatus.SUCCEEDED
FAILED = ScheduledJobRunStatus.FAILED


@pytest.fixture
def job(db):
    account = User(
        email="reporter@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.SERVICE_ACCOUNT,
    )
    db.add(account)
    db.flush()
    job = ScheduledJob(
        id="chrysalis-staging",
        machine=db.query(Machine).filter_by(name="chrysalis").one(),
        scan_mode="staging",
        service_account_id=account.id,
        max_silence_minutes=30,
        max_duration_minutes=20,
    )
    db.add(job)
    db.flush()

    return job


def _run(db, job, status, started_minutes_ago, finished_minutes_ago=None):
    reported_at = NOW - timedelta(minutes=started_minutes_ago)
    finish_reported_at = (
        None
        if finished_minutes_ago is None
        else NOW - timedelta(minutes=finished_minutes_ago)
    )
    run = ScheduledJobRun(
        id=uuid4(),
        job_id=job.id,
        status=status,
        started_at=reported_at,
        reported_at=reported_at,
        finished_at=finish_reported_at,
        finish_reported_at=finish_reported_at,
        exit_code=None if status == RUNNING else int(status == FAILED),
    )
    db.add(run)
    db.flush()

    return run


def _health(db):
    [job_health] = summarize_job_health(db, NOW)

    return job_health


def test_never_reported_job_is_stale(db, job):
    health = _health(db)

    assert health.health == "stale"
    assert health.last_reported_at is None
    assert health.latest_completed_run is None
    assert health.active_run is None


def test_recent_success_is_healthy(db, job):
    run = _run(db, job, SUCCEEDED, 15, 10)

    health = _health(db)

    assert health.health == "healthy"
    assert health.last_reported_at == NOW - timedelta(minutes=10)
    assert health.latest_completed_run.id == run.id


def test_latest_reported_failure_is_failed(db, job):
    _run(db, job, SUCCEEDED, 25, 20)
    _run(db, job, FAILED, 15, 10)

    assert _health(db).health == "failed"


def test_run_within_allowed_duration_is_running(db, job):
    run = _run(db, job, RUNNING, 19)

    health = _health(db)

    assert health.health == "running"
    assert health.active_run.id == run.id
    assert health.latest_completed_run is None


def test_long_run_within_allowed_duration_is_not_silent(db, job):
    job.max_duration_minutes = 60
    _run(db, job, RUNNING, 45)

    assert _health(db).health == "running"


def test_missing_completion_is_stale_not_failed(db, job):
    completed = _run(db, job, SUCCEEDED, 25, 22)
    _run(db, job, RUNNING, 21)

    health = _health(db)

    assert health.health == "stale"
    assert health.active_run is None
    assert health.latest_completed_run.id == completed.id


def test_missing_scheduled_activity_is_stale(db, job):
    _run(db, job, SUCCEEDED, 40, 31)

    assert _health(db).health == "stale"


def test_overlapping_runs_preserve_latest_completed_outcome(db, job):
    failed = _run(db, job, FAILED, 18, 2)
    _run(db, job, RUNNING, 10)
    newest = _run(db, job, RUNNING, 5)

    health = _health(db)

    assert health.health == "failed"
    assert health.latest_completed_run.id == failed.id
    assert health.active_run.id == newest.id
    assert health.active_run_count == 2
    assert health.last_reported_at == NOW - timedelta(minutes=2)


def test_success_after_an_abandoned_run_is_healthy(db, job):
    _run(db, job, RUNNING, 29)
    _run(db, job, SUCCEEDED, 5, 1)

    assert _health(db).health == "healthy"
