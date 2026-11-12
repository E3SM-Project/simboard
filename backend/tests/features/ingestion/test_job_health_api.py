"""Scheduled job registration, run reporting, authorization, and idempotency."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.api.version import API_BASE
from app.features.ingestion.models import ScheduledJobRun
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app

JOBS_URL = f"{API_BASE}/ingestions/jobs"
JOB_ID = "chrysalis-staging"
STARTED_AT = "2026-01-02T00:00:00+00:00"
FINISHED_AT = "2026-01-02T00:05:00+00:00"
SUCCESS = {"started_at": STARTED_AT, "finished_at": FINISHED_AT, "exit_code": 0}
FAILURE = {
    "started_at": STARTED_AT,
    "finished_at": FINISHED_AT,
    "exit_code": 1,
    "failure": {
        "reason": "api_request",
        "message": "State request failed.",
        "status_code": 503,
        "transient": True,
    },
}


@pytest.fixture
def users(db, admin_user_sync, normal_user_sync):
    def service_account(email):
        user = User(
            email=email,
            is_active=True,
            is_verified=True,
            role=UserRole.SERVICE_ACCOUNT,
        )
        db.add(user)
        db.commit()

        return user

    return {
        "admin": db.get(User, admin_user_sync["id"]),
        "user": db.get(User, normal_user_sync["id"]),
        "reporter": service_account("chrysalis-ingestion@example.com"),
        "other": service_account("perlmutter-ingestion@example.com"),
    }


@pytest.fixture
def act_as(client):
    def set_user(user):
        app.dependency_overrides[current_active_user] = lambda: user

    yield set_user
    app.dependency_overrides.pop(current_active_user, None)


@pytest.fixture
def job(client, users, act_as):
    _register(client, act_as, users["admin"], JOB_ID)
    act_as(users["reporter"])


def _register(client, act_as, admin, job_id, **overrides):
    act_as(admin)
    payload = {
        "machine_name": "chrysalis",
        "scan_mode": "staging",
        "service_account_email": "chrysalis-ingestion@example.com",
        "max_silence_minutes": 30,
        "max_duration_minutes": 20,
        **overrides,
    }

    return client.put(f"{JOBS_URL}/{job_id}", json=payload)


def _run_url(run_id, action, job_id=JOB_ID):
    return f"{JOBS_URL}/{job_id}/runs/{run_id}/{action}"


def test_only_admins_register_jobs_for_known_service_accounts(client, users, act_as):
    assert _register(client, act_as, users["reporter"], JOB_ID).status_code == 403

    response = _register(client, act_as, users["admin"], JOB_ID)
    assert response.status_code == 200
    assert response.json() == {
        "id": JOB_ID,
        "machine_name": "chrysalis",
        "scan_mode": "staging",
        "max_silence_minutes": 30,
        "max_duration_minutes": 20,
    }

    updated = _register(client, act_as, users["admin"], JOB_ID, max_silence_minutes=45)
    assert updated.json()["max_silence_minutes"] == 45

    not_service = _register(
        client,
        act_as,
        users["admin"],
        JOB_ID,
        service_account_email="admin@example.com",
    )
    assert not_service.status_code == 404
    unknown_machine = _register(
        client, act_as, users["admin"], JOB_ID, machine_name="unknown"
    )
    assert unknown_machine.status_code == 404
    assert _register(client, act_as, users["admin"], "Bad ID").status_code == 422
    assert (
        _register(client, act_as, users["admin"], JOB_ID, scan_mode="other").status_code
        == 422
    )


@pytest.mark.parametrize("role", ["admin", "user", "other"])
def test_only_the_bound_service_account_reports_runs(client, users, act_as, job, role):
    act_as(users[role])
    run_id = uuid4()

    start = client.put(_run_url(run_id, "start"), json={"started_at": STARTED_AT})
    finish = client.put(_run_url(run_id, "finish"), json=SUCCESS)

    assert start.status_code == 403
    assert finish.status_code == 403


def test_reports_for_unregistered_jobs_are_rejected(client, users, act_as):
    act_as(users["reporter"])

    response = client.put(
        _run_url(uuid4(), "start", job_id="unknown"), json={"started_at": STARTED_AT}
    )

    assert response.status_code == 404


def test_start_and_finish_persist_once_across_retries(client, db, job):
    run_id = uuid4()

    for _ in range(2):
        start = client.put(_run_url(run_id, "start"), json={"started_at": STARTED_AT})
        assert start.status_code == 200
        assert start.json()["status"] == "running"
    for _ in range(2):
        finish = client.put(_run_url(run_id, "finish"), json=SUCCESS)
        assert finish.status_code == 200
    # A late start retry must not reopen a finished run.
    late_start = client.put(_run_url(run_id, "start"), json={"started_at": STARTED_AT})

    run = db.query(ScheduledJobRun).one()
    assert late_start.json()["status"] == "succeeded"
    assert run.id == run_id
    assert run.job_id == JOB_ID
    assert run.status == "succeeded"
    assert run.exit_code == 0
    assert run.started_at == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert run.finished_at == datetime(2026, 1, 2, 0, 5, tzinfo=timezone.utc)
    assert run.finish_reported_at >= run.reported_at
    assert run.failure_reason is None


def test_finish_without_start_records_the_failure(client, db, job):
    run_id = uuid4()

    response = client.put(_run_url(run_id, "finish"), json=FAILURE)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["exit_code"] == 1
    assert body["failure_reason"] == "api_request"
    assert body["failure_message"] == "State request failed."
    assert body["failure_status_code"] == 503
    assert body["failure_transient"] is True
    assert db.query(ScheduledJobRun).count() == 1


def test_reports_cannot_change_an_outcome_or_another_jobs_run(
    client, users, act_as, job
):
    run_id = uuid4()
    client.put(_run_url(run_id, "finish"), json=SUCCESS)

    changed = client.put(_run_url(run_id, "finish"), json=FAILURE)

    _register(client, act_as, users["admin"], "chrysalis-archive", scan_mode="archive")
    act_as(users["reporter"])
    other_job_start = client.put(
        _run_url(run_id, "start", job_id="chrysalis-archive"),
        json={"started_at": STARTED_AT},
    )
    other_job_finish = client.put(
        _run_url(run_id, "finish", job_id="chrysalis-archive"), json=SUCCESS
    )

    assert changed.status_code == 409
    assert other_job_start.status_code == 409
    assert other_job_finish.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {**SUCCESS, "exit_code": 1},
        {**SUCCESS, "failure": FAILURE["failure"]},
        {**FAILURE, "failure": {**FAILURE["failure"], "message": "x" * 501}},
        {**FAILURE, "failure": {**FAILURE["failure"], "reason": "other"}},
        {**SUCCESS, "finished_at": "2026-01-02T00:05:00"},
    ],
    ids=["missing-failure", "unexpected-failure", "long-message", "reason", "naive"],
)
def test_invalid_finish_reports_are_rejected(client, job, payload):
    response = client.put(_run_url(uuid4(), "finish"), json=payload)

    assert response.status_code == 422


def test_new_runs_prune_records_past_retention(client, db, job):
    old_run_id = uuid4()
    client.put(_run_url(old_run_id, "finish"), json=SUCCESS)
    old_run = db.get(ScheduledJobRun, old_run_id)
    old_run.reported_at -= timedelta(days=91)
    db.commit()

    client.put(_run_url(uuid4(), "start"), json={"started_at": STARTED_AT})

    db.expire_all()
    assert db.get(ScheduledJobRun, old_run_id) is None
    assert db.query(ScheduledJobRun).count() == 1


def test_health_is_protected_and_filterable(client, users, act_as, job):
    act_as(users["user"])
    assert client.get(JOBS_URL).status_code == 403

    act_as(users["other"])
    response = client.get(JOBS_URL)
    filtered = client.get(JOBS_URL, params={"machine_name": "perlmutter"})

    assert response.status_code == 200
    [listed] = response.json()["jobs"]
    assert listed["id"] == JOB_ID
    assert listed["machine_name"] == "chrysalis"
    assert listed["health"] == "stale"
    assert listed["last_reported_at"] is None
    assert filtered.json() == {"jobs": []}
    assert client.get(JOBS_URL, params={"machine_name": "x"}).status_code == 404
