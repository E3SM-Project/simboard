"""UTC execution reporting, authorization, totals, and repeat submissions."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.api.version import API_BASE
from app.features.catalog.models import Execution
from app.features.ingestion.enums import IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app
from tests.features.catalog.test_models import (
    _create_case,
    _create_execution,
    _create_ingestion,
)
from tests.fixtures.continuation_case import EXECUTIONS, stage_continuation_case

SUMMARY_URL = f"{API_BASE}/ingestions/summary"
RANGE = {"start_date": "2026-01-02", "end_date": "2026-01-04"}


@pytest.fixture
def summary_user(client, db, admin_user_sync):
    user = db.get(User, admin_user_sync["id"])

    def authenticated_user():
        return user

    app.dependency_overrides[current_active_user] = authenticated_user
    yield user
    app.dependency_overrides.pop(current_active_user, None)


@pytest.fixture
def summary_data(db, summary_user):
    perlmutter = db.query(Machine).filter_by(name="perlmutter").one()
    chrysalis = db.query(Machine).filter_by(name="chrysalis").one()
    cases = [
        _create_case(db, name="same-case", machine=machine, hpc_username=username)
        for machine, username in [
            (perlmutter, "alice"),
            (perlmutter, "bob"),
            (chrysalis, "alice"),
        ]
    ]
    ingestion = _create_ingestion(
        db,
        machine_id=chrysalis.id,
        user_id=summary_user.id,
        source_reference="summary-fixture",
    )
    ingestion.status = IngestionStatus.PARTIAL
    ingestion.error_count = 1
    # Deliberately differs from the actual row count and some cases' machines.
    ingestion.created_count = 999
    for index, (case, timestamp) in enumerate(
        [
            (cases[0], "2026-01-01T23:59:59.999999+00:00"),
            (cases[0], "2026-01-02T00:00:00+00:00"),
            (cases[0], "2026-01-02T23:59:59.999999+00:00"),
            (cases[0], "2026-01-03T00:00:00+00:00"),
            (cases[1], "2026-01-02T08:00:00+00:00"),
            (cases[2], "2026-01-02T10:00:00+00:00"),
            (cases[2], "2026-01-04T00:00:00+00:00"),
        ]
    ):
        execution = _create_execution(
            db,
            case_id=case.id,
            ingestion_id=ingestion.id,
            user_id=summary_user.id,
            execution_id=f"summary-{index}",
        )
        execution.created_at = datetime.fromisoformat(timestamp)
    db.flush()

    return cases


def test_summary_requires_authentication(client):
    response = client.get(SUMMARY_URL, params=RANGE)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "role,status_code",
    [(UserRole.USER, 403), (UserRole.ADMIN, 200), (UserRole.SERVICE_ACCOUNT, 200)],
)
def test_summary_requires_ingestion_access(client, summary_user, role, status_code):
    summary_user.role = role
    response = client.get(SUMMARY_URL, params=RANGE)
    assert response.status_code == status_code, response.text
    if status_code == 403:
        assert response.json() == {
            "detail": "Only administrators and service accounts may read summaries."
        }


def test_ingestion_state_denial_message_is_unchanged(client, summary_user):
    summary_user.role = UserRole.USER
    response = client.get(
        f"{API_BASE}/ingestions/archive-checkpoints",
        params={"machine_name": "perlmutter", "archive_name": "test-archive"},
    )
    assert response.status_code == 403, response.text
    assert response.json() == {
        "detail": "Only administrators and service accounts may manage ingestion state."
    }


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start_date": "2026-01-02"},
        {"end_date": "2026-01-04"},
        {**RANGE, "start_date": "not-a-date"},
        {**RANGE, "end_date": "2026-02-30"},
        {"start_date": "2026-01-04", "end_date": "2026-01-02"},
        {"start_date": "2026-01-02", "end_date": "2026-01-02"},
        {"start_date": "2026-01-01", "end_date": "2026-04-02"},
    ],
)
def test_summary_rejects_invalid_ranges(client, summary_user, params):
    response = client.get(SUMMARY_URL, params=params)
    assert response.status_code == 422, response.text


def test_summary_accepts_exactly_90_days(client, summary_user):
    response = client.get(
        SUMMARY_URL, params={"start_date": "2026-01-01", "end_date": "2026-04-01"}
    )
    assert response.status_code == 200, response.text


def test_summary_counts_actual_rows_and_distinct_cases(client, summary_data):
    alice, bob, other_machine = summary_data
    response = client.get(SUMMARY_URL, params=RANGE)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rows": [
            _case_row("2026-01-02", other_machine, "chrysalis", 1),
            _case_row("2026-01-02", alice, "perlmutter", 2),
            _case_row("2026-01-02", bob, "perlmutter", 1),
            _case_row("2026-01-03", alice, "perlmutter", 1),
        ],
        "daily_machine_totals": [
            {
                "day": "2026-01-02",
                "machine": "chrysalis",
                "new_executions": 1,
                "distinct_cases": 1,
            },
            {
                "day": "2026-01-02",
                "machine": "perlmutter",
                "new_executions": 3,
                "distinct_cases": 2,
            },
            {
                "day": "2026-01-03",
                "machine": "perlmutter",
                "new_executions": 1,
                "distinct_cases": 1,
            },
        ],
        "daily_totals": [
            {"day": "2026-01-02", "new_executions": 4, "distinct_cases": 3},
            {"day": "2026-01-03", "new_executions": 1, "distinct_cases": 1},
        ],
        "totals": {"new_executions": 5, "distinct_cases": 3},
    }


@pytest.mark.parametrize("zone", ["America/Los_Angeles", "Asia/Tokyo"])
def test_summary_uses_utc_boundaries_and_buckets(client, db, summary_data, zone):
    utc = client.get(SUMMARY_URL, params=RANGE)
    assert utc.status_code == 200, utc.text
    db.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
    response = client.get(SUMMARY_URL, params=RANGE)
    assert response.status_code == 200, response.text
    assert response.json() == utc.json()
    assert response.json()["totals"] == {"new_executions": 5, "distinct_cases": 3}


@pytest.mark.parametrize("machine_name", ["perlmutter", "pm", "pm-cpu", "pm-gpu"])
def test_summary_filters_on_case_machine(client, summary_data, machine_name):
    response = client.get(SUMMARY_URL, params={**RANGE, "machine_name": machine_name})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["machine"] for row in body["rows"]} == {"perlmutter"}
    assert body["totals"] == {"new_executions": 4, "distinct_cases": 2}
    assert body["daily_totals"] == [
        {"day": "2026-01-02", "new_executions": 3, "distinct_cases": 2},
        {"day": "2026-01-03", "new_executions": 1, "distinct_cases": 1},
    ]


@pytest.mark.parametrize(
    "filters,machines,new_executions",
    [
        ({"site_name": "NERSC"}, {"perlmutter"}, 4),
        ({"site_name": "lcrc"}, {"chrysalis"}, 1),
        ({"site_name": "NERSC", "machine_name": "perlmutter"}, {"perlmutter"}, 4),
        ({"site_name": "LCRC", "machine_name": "perlmutter"}, set(), 0),
    ],
)
def test_summary_filters_on_case_site(
    client, summary_data, filters, machines, new_executions
):
    response = client.get(SUMMARY_URL, params={**RANGE, **filters})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["machine"] for row in body["rows"]} == machines
    assert body["totals"]["new_executions"] == new_executions


@pytest.mark.parametrize("filters", [{"machine_name": "x"}, {"site_name": "x"}])
def test_summary_rejects_unknown_machine_or_site(client, summary_user, filters):
    response = client.get(SUMMARY_URL, params={**RANGE, **filters})
    assert response.status_code == 404


def test_summary_returns_empty_collections_and_zero_totals(client, summary_data):
    response = client.get(
        SUMMARY_URL, params={"start_date": "2025-01-01", "end_date": "2025-01-02"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rows": [],
        "daily_machine_totals": [],
        "daily_totals": [],
        "totals": {"new_executions": 0, "distinct_cases": 0},
    }


@pytest.mark.parametrize("partial", [False, True])
def test_summary_ignores_repeated_ingestion_and_metadata_backfill(
    client, db, summary_user, tmp_path, partial
):
    case_path = stage_continuation_case(tmp_path)
    if partial:
        invalid = case_path / next(iter(EXECUTIONS))
        next(invalid.glob("e3sm_timing.*")).write_text("Case : missing-lid\n")
    payload = {"archive_path": str(case_path), "machine_name": "chrysalis"}
    first = client.post(f"{API_BASE}/ingestions/from-path", json=payload)
    assert first.status_code == 201, first.text
    expected_count = len(EXECUTIONS) - int(partial)
    assert first.json()["created_count"] == expected_count
    assert db.query(Ingestion).one().status == ("partial" if partial else "success")

    for execution in db.query(Execution).all():
        execution.created_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    db.commit()
    before_dates = dict(db.query(Execution.id, Execution.created_at).all())
    before = client.get(SUMMARY_URL, params=RANGE).json()
    assert before["totals"] == {"new_executions": expected_count, "distinct_cases": 1}

    repeated = client.post(f"{API_BASE}/ingestions/from-path", json=payload)
    assert repeated.status_code == (400 if partial else 200), repeated.text
    assert repeated.json()["created_count"] == 0
    assert repeated.json()["duplicate_count"] == expected_count
    assert client.get(SUMMARY_URL, params=RANGE).json() == before

    execution = db.query(Execution).first()
    backfill = client.post(
        f"{API_BASE}/ingestions/metadata-backfill",
        json={
            "machine_name": "chrysalis",
            "record_id": str(execution.id),
            "case_name": execution.case.name,
            "hpc_username": execution.case.hpc_username,
            "execution_id": execution.execution_id,
            "fields": ["grid"],
            "values": {"grid_long_name": "updated-grid", "grid_alias": None},
            "expected": {
                "grid_long_name": execution.grid_long_name,
                "grid_alias": execution.grid_alias,
            },
            "overwrite": True,
            "dry_run": False,
        },
    )
    assert backfill.status_code == 200, backfill.text
    assert backfill.json()["outcome"] == "changed"
    assert client.get(SUMMARY_URL, params=RANGE).json() == before
    assert dict(db.query(Execution.id, Execution.created_at).all()) == before_dates


def _case_row(day, case, machine, count):
    return {
        "day": day,
        "machine": machine,
        "case_id": str(case.id),
        "case_name": case.name,
        "hpc_username": case.hpc_username,
        "new_executions": count,
    }
