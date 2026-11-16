"""Scheduled job registration, run reporting, authorization, and idempotency."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.api.version import API_BASE
from app.features.ingestion.models import ScheduledJob, ScheduledJobRun
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app

JOBS_URL = f"{API_BASE}/ingestions/jobs"
JOB_ID = "chrysalis-staging"
STARTED_AT = "2026-01-02T00:00:00+00:00"
FINISHED_AT = "2026-01-02T00:05:00+00:00"
IDENTITY = {"machine_name": "chrysalis", "scan_mode": "staging"}
ARCHIVE = {"scan_mode": "archive"}
START = {**IDENTITY, "started_at": STARTED_AT}
SUCCESS = {**START, "finished_at": FINISHED_AT, "exit_code": 0}
FAILURE = {
    **START,
    "finished_at": FINISHED_AT,
    "exit_code": 1,
    "failure": {
        "reason": "api_request",
        "message": "State request failed.",
        "status_code": 503,
        "transient": True,
    },
}
UPLOAD_FAILURES = {
    "counts": {"413": 2, "network": 1, "404": 1},
    "cases": [
        {
            "case_path": "/archive/case-a",
            "status_code": 413,
            "attempts": 1,
            "message": "HTTP 413: <html>413 Request Entity Too Large</html>",
        },
        {
            "case_path": "/archive/case-b",
            "status_code": None,
            "attempts": 3,
            "message": "Request timed out",
        },
    ],
    "truncated": True,
}
UPLOAD_FAILURE = UPLOAD_FAILURES["cases"][0]


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


def _daily_count(day, machine_name, category, count):
    return {
        "day": day,
        "machine_name": machine_name,
        "category": category,
        "count": count,
    }


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
    too_long = _register(
        client, act_as, users["admin"], JOB_ID, max_duration_minutes=2**31
    )
    assert too_long.status_code == 422
    assert (
        _register(client, act_as, users["admin"], JOB_ID, scan_mode="other").status_code
        == 422
    )


@pytest.mark.parametrize("role", ["admin", "user", "other"])
def test_only_the_bound_service_account_reports_runs(client, users, act_as, job, role):
    act_as(users[role])
    run_id = uuid4()

    start = client.put(_run_url(run_id, "start"), json=START)
    finish = client.put(_run_url(run_id, "finish"), json=SUCCESS)

    assert start.status_code == 403
    assert finish.status_code == 403


@pytest.mark.parametrize("action", ["start", "finish"])
@pytest.mark.parametrize(
    ("scan_mode", "thresholds"),
    [("staging", (45, 60)), ("archive", (1560, 720)), ("diagnostics", (420, 300))],
)
def test_first_report_registers_the_job(
    client, db, users, act_as, action, scan_mode, thresholds
):
    job_id = f"chrysalis-{scan_mode}"
    payload = {**(START if action == "start" else SUCCESS), "scan_mode": scan_mode}
    act_as(users["reporter"])

    response = client.put(_run_url(uuid4(), action, job_id=job_id), json=payload)

    registered = db.get(ScheduledJob, job_id)
    assert response.status_code == 200
    assert registered.service_account_id == users["reporter"].id
    assert registered.machine.name == "chrysalis"
    assert registered.scan_mode == scan_mode
    assert (
        registered.max_silence_minutes,
        registered.max_duration_minutes,
    ) == thresholds
    # The registering account owns the job.
    act_as(users["other"])
    other = client.put(_run_url(uuid4(), "start", job_id=job_id), json=payload)
    assert other.status_code == 403


def test_unregistered_reports_need_a_service_account_and_known_machine(
    client, db, users, act_as
):
    url = _run_url(uuid4(), "start")
    # Other callers cannot probe or register job IDs.
    act_as(users["user"])
    probe = client.put(url, json=START)
    act_as(users["reporter"])
    unknown_machine = client.put(url, json={**START, "machine_name": "unknown"})
    missing_identity = client.put(url, json={"started_at": STARTED_AT})

    assert probe.status_code == 403
    assert unknown_machine.status_code == 404
    assert missing_identity.status_code == 422
    assert db.get(ScheduledJob, JOB_ID) is None


@pytest.mark.parametrize(("action", "payload"), [("start", START), ("finish", SUCCESS)])
@pytest.mark.parametrize(
    "identity", [{"machine_name": "perlmutter"}, ARCHIVE], ids=["machine", "mode"]
)
def test_reports_for_another_machine_or_mode_conflict(
    client, db, job, action, payload, identity
):
    response = client.put(_run_url(uuid4(), action), json={**payload, **identity})

    assert response.status_code == 409
    assert db.query(ScheduledJobRun).count() == 0


def test_reports_keep_preregistered_thresholds(client, db, job):
    assert client.put(_run_url(uuid4(), "start"), json=START).status_code == 200

    registered = db.get(ScheduledJob, JOB_ID)
    assert (registered.max_silence_minutes, registered.max_duration_minutes) == (30, 20)


def test_start_and_finish_persist_once_across_retries(client, db, job):
    run_id = uuid4()

    for _ in range(2):
        start = client.put(_run_url(run_id, "start"), json=START)
        assert start.status_code == 200
        assert start.json()["status"] == "running"
    for _ in range(2):
        finish = client.put(_run_url(run_id, "finish"), json=SUCCESS)
        assert finish.status_code == 200
    # A late start retry must not reopen a finished run.
    late_start = client.put(_run_url(run_id, "start"), json=START)

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
        json={**START, **ARCHIVE},
    )
    other_job_finish = client.put(
        _run_url(run_id, "finish", job_id="chrysalis-archive"),
        json={**SUCCESS, **ARCHIVE},
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
        {**FAILURE, "exit_code": 256},
        {**FAILURE, "failure": {**FAILURE["failure"], "status_code": 2**31}},
        {
            **FAILURE,
            "upload_failures": {**UPLOAD_FAILURES, "cases": [UPLOAD_FAILURE] * 51},
        },
        {**FAILURE, "upload_failures": {**UPLOAD_FAILURES, "counts": {"timeout": 1}}},
        {**FAILURE, "upload_failures": {**UPLOAD_FAILURES, "counts": {"413": 0}}},
        {**FAILURE, "upload_failures": {**UPLOAD_FAILURES, "counts": {"413": 1}}},
        {**FAILURE, "upload_failures": {**UPLOAD_FAILURES, "truncated": False}},
        {
            **FAILURE,
            "upload_failures": {
                **UPLOAD_FAILURES,
                "cases": [{**UPLOAD_FAILURE, "message": "x" * 201}],
            },
        },
    ],
    ids=[
        "missing-failure",
        "unexpected-failure",
        "long-message",
        "reason",
        "naive",
        "exit-code-range",
        "status-code-range",
        "too-many-upload-cases",
        "upload-count-key",
        "upload-count-value",
        "uncounted-upload-cases",
        "untruncated-upload-cases",
        "long-upload-message",
    ],
)
def test_invalid_finish_reports_are_rejected(client, job, payload):
    response = client.put(_run_url(uuid4(), "finish"), json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("action", ["start", "finish"])
def test_new_runs_prune_only_their_jobs_records_past_retention(
    client, db, users, act_as, job, action
):
    _register(client, act_as, users["admin"], "chrysalis-archive", scan_mode="archive")
    act_as(users["reporter"])
    old_run_id, other_job_run_id = uuid4(), uuid4()
    client.put(_run_url(old_run_id, "finish"), json=SUCCESS)
    client.put(
        _run_url(other_job_run_id, "finish", job_id="chrysalis-archive"),
        json={**SUCCESS, **ARCHIVE},
    )
    for run_id in (old_run_id, other_job_run_id):
        db.get(ScheduledJobRun, run_id).reported_at -= timedelta(days=91)
    db.commit()

    payload = START if action == "start" else SUCCESS
    client.put(_run_url(uuid4(), action), json=payload)

    db.expire_all()
    assert db.get(ScheduledJobRun, old_run_id) is None
    assert db.get(ScheduledJobRun, other_job_run_id) is not None


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
    assert filtered.json() == {"jobs": [], "upload_failure_daily_counts": []}
    assert client.get(JOBS_URL, params={"machine_name": "x"}).status_code == 404


def test_health_filters_by_site(client, users, act_as, job):
    act_as(users["admin"])

    def job_ids(**params):
        response = client.get(JOBS_URL, params=params)
        assert response.status_code == 200, response.text

        return [listed["id"] for listed in response.json()["jobs"]]

    assert job_ids(site_name="LCRC") == [JOB_ID]
    assert job_ids(site_name="NERSC") == []
    assert job_ids(site_name="NERSC", machine_name="chrysalis") == []
    assert client.get(JOBS_URL, params={"site_name": "x"}).status_code == 404


def test_latest_upload_run_lists_failed_uploads_until_they_succeed(client, db, job):
    run_id = uuid4()
    failed = {**FAILURE, "upload_failures": UPLOAD_FAILURES}

    first = client.put(_run_url(run_id, "finish"), json=failed)
    retry = client.put(_run_url(run_id, "finish"), json=failed)
    changed = client.put(
        _run_url(run_id, "finish"),
        json={
            **failed,
            "upload_failures": {**UPLOAD_FAILURES, "counts": {"413": 3, "network": 1}},
        },
    )
    [listed] = client.get(JOBS_URL).json()["jobs"]

    assert first.json()["upload_failures"] == UPLOAD_FAILURES
    assert retry.status_code == 200
    assert changed.status_code == 409
    assert listed["latest_upload_run"]["upload_failures"] == UPLOAD_FAILURES

    # A run that ends before uploading keeps the stuck cases listed.
    client.put(_run_url(uuid4(), "finish"), json=FAILURE)

    [listed] = client.get(JOBS_URL).json()["jobs"]
    assert listed["latest_completed_run"]["upload_failures"] is None
    assert listed["latest_upload_run"]["id"] == str(run_id)
    assert (
        db.query(ScheduledJobRun)
        .filter(ScheduledJobRun.upload_failures.is_(None))
        .count()
        == 1
    )

    no_failures = {"counts": {}, "cases": [], "truncated": False}
    client.put(
        _run_url(uuid4(), "finish"), json={**SUCCESS, "upload_failures": no_failures}
    )

    [listed] = client.get(JOBS_URL).json()["jobs"]
    assert listed["latest_upload_run"]["upload_failures"] == no_failures


def test_daily_upload_failure_counts_by_category_and_machine(
    client, db, users, act_as, job
):
    def finish(counts, reported_at, job_id=JOB_ID, machine_name="chrysalis"):
        run_id = uuid4()
        truncated = sum(counts.values()) > len(UPLOAD_FAILURES["cases"])
        uploads = {**UPLOAD_FAILURES, "counts": counts, "truncated": truncated}
        payload = {**FAILURE, "machine_name": machine_name, "upload_failures": uploads}
        assert client.put(_run_url(run_id, "finish", job_id), json=payload).is_success
        db.get(ScheduledJobRun, run_id).finish_reported_at = reported_at

    day_1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    finish({"413": 2, "network": 1, "404": 1}, day_1 + timedelta(hours=23.5))
    finish({"503": 2, "409": 1}, day_1 + timedelta(hours=24.5))
    client.put(_run_url(uuid4(), "finish"), json=SUCCESS)
    act_as(users["other"])
    finish({"401": 1, "500": 1}, day_1, "perlmutter-staging", "perlmutter")
    db.commit()

    counts = client.get(JOBS_URL).json()["upload_failure_daily_counts"]
    filtered = client.get(JOBS_URL, params={"machine_name": "perlmutter"}).json()

    perlmutter = [
        _daily_count("2026-01-01", "perlmutter", "auth", 1),
        _daily_count("2026-01-01", "perlmutter", "server", 1),
    ]
    assert counts == [
        _daily_count("2026-01-01", "chrysalis", "bad_upload", 2),
        _daily_count("2026-01-01", "chrysalis", "other", 1),
        _daily_count("2026-01-01", "chrysalis", "unavailable", 1),
        *perlmutter,
        _daily_count("2026-01-02", "chrysalis", "conflict", 1),
        _daily_count("2026-01-02", "chrysalis", "unavailable", 2),
    ]
    assert filtered["upload_failure_daily_counts"] == perlmutter
    by_site = client.get(JOBS_URL, params={"site_name": "NERSC"}).json()
    assert by_site["upload_failure_daily_counts"] == perlmutter
