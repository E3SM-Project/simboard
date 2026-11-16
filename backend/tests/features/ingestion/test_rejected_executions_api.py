"""Rejected execution groups, authorization, filters, and date ranges."""

from datetime import datetime, timezone

import pytest

from app.api.version import API_BASE
from app.features.ingestion.enums import ExecutionDiscoveryOutcome
from app.features.ingestion.models import ExecutionDiscoveryResult
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app

REJECTED_URL = f"{API_BASE}/ingestions/rejected-executions"
# Counts executions first detected on 2026-11-03 and 2026-11-04 as new.
RANGE = {"start_date": "2026-11-03", "end_date": "2026-11-05"}
FIELD_ERROR = {
    "field": "case_name",
    "code": "missing",
    "message": "case_name is required.",
}
FILE_ERROR = {
    "code": "missing_required_file",
    "file_spec": "env_case.xml.*.gz",
    "message": "Missing required 'env_case.xml.*.gz' in casedocs/.",
}
INCOMPLETE = ExecutionDiscoveryOutcome.REJECTED_INCOMPLETE
INVALID = ExecutionDiscoveryOutcome.REJECTED_INVALID


@pytest.fixture
def reader(client, db, admin_user_sync):
    # Other tests commit discovery rows on separate connections; start empty.
    # The deletion rolls back with this test's transaction.
    db.query(ExecutionDiscoveryResult).delete()
    user = db.get(User, admin_user_sync["id"])
    app.dependency_overrides[current_active_user] = lambda: user
    yield user
    app.dependency_overrides.pop(current_active_user, None)


@pytest.fixture
def results(db, reader):
    machines = {
        name: db.query(Machine).filter_by(name=name).one()
        for name in ("perlmutter", "chrysalis")
    }
    for machine_name, case_identity, execution_id, outcome, errors, day in [
        ("perlmutter", "user/case-a", "1", INCOMPLETE, None, 1),
        ("perlmutter", "user/case-b", "2", INVALID, [FIELD_ERROR], 3),
        ("perlmutter", "user/case-d", "5", INVALID, [FIELD_ERROR], 2),
        ("perlmutter", "user/case-a", "3", ExecutionDiscoveryOutcome.ACCEPTED, None, 4),
        ("chrysalis", "user/case-c", "4", INCOMPLETE, [FILE_ERROR, FIELD_ERROR], 4),
        ("chrysalis", "user/case-c", "6", INCOMPLETE, [FILE_ERROR], 5),
    ]:
        db.add(
            ExecutionDiscoveryResult(
                machine_id=machines[machine_name].id,
                case_identity=case_identity,
                execution_id=execution_id,
                outcome=outcome,
                errors=errors,
                created_at=datetime(2026, 11, day, tzinfo=timezone.utc),
            )
        )
    db.commit()


def _group(site, outcome, code, target, counts, latest_day, example):
    executions, cases, new_in_range = counts
    machine_name, case_identity, execution_id, message = example

    return {
        "site_name": site,
        "outcome": outcome,
        "code": code,
        "target": target,
        "executions": executions,
        "cases": cases,
        "new_in_range": new_in_range,
        "latest_detected_at": datetime(2026, 11, latest_day, tzinfo=timezone.utc),
        "example": {
            "machine_name": machine_name,
            "case_identity": case_identity,
            "execution_id": execution_id,
            "message": message,
        },
    }


def _get(client, **params):
    response = client.get(REJECTED_URL, params={**RANGE, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    for group in body["groups"]:
        group["latest_detected_at"] = datetime.fromisoformat(
            group["latest_detected_at"]
        )

    return body


def test_rejected_executions_require_authentication(client):
    assert client.get(REJECTED_URL, params=RANGE).status_code == 401


@pytest.mark.parametrize(
    "role,status_code",
    [(UserRole.USER, 403), (UserRole.ADMIN, 200), (UserRole.SERVICE_ACCOUNT, 200)],
)
def test_rejected_executions_require_ingestion_access(
    client, reader, role, status_code
):
    reader.role = role
    response = client.get(REJECTED_URL, params=RANGE)
    assert response.status_code == status_code, response.text


def test_groups_current_rejections_by_site_outcome_and_first_error(client, db, results):
    assert _get(client) == {
        "groups": [
            _group(
                "LCRC",
                "rejected_incomplete",
                "missing_required_file",
                "env_case.xml.*.gz",
                (2, 1, 1),
                5,
                ("chrysalis", "user/case-c", "6", FILE_ERROR["message"]),
            ),
            _group(
                "NERSC",
                "rejected_invalid",
                "missing",
                "case_name",
                (2, 2, 1),
                3,
                ("perlmutter", "user/case-b", "2", FIELD_ERROR["message"]),
            ),
            _group(
                "NERSC",
                "rejected_incomplete",
                None,
                None,
                (1, 1, 0),
                1,
                ("perlmutter", "user/case-a", "1", None),
            ),
        ],
        "total": 5,
        "new_in_range": 2,
    }

    # Revalidation that accepts an execution removes it from its group.
    db.query(ExecutionDiscoveryResult).filter_by(
        execution_id="6"
    ).one().outcome = ExecutionDiscoveryOutcome.ACCEPTED
    db.commit()
    body = _get(client)
    assert (body["total"], body["new_in_range"]) == (4, 2)
    lcrc = next(group for group in body["groups"] if group["site_name"] == "LCRC")
    assert (lcrc["executions"], lcrc["example"]["execution_id"]) == (1, "4")


@pytest.mark.parametrize(
    "filters,total",
    [
        ({"machine_name": "pm-cpu"}, 3),
        ({"site_name": "LCRC"}, 2),
        ({"site_name": "nersc"}, 3),
        ({"site_name": "LCRC", "machine_name": "perlmutter"}, 0),
    ],
)
def test_filters_by_machine_and_site(client, results, filters, total):
    body = _get(client, **filters)
    assert sum(group["executions"] for group in body["groups"]) == total
    assert body["total"] == total


@pytest.mark.parametrize("filters", [{"machine_name": "x"}, {"site_name": "x"}])
def test_rejects_unknown_machine_or_site(client, reader, filters):
    response = client.get(REJECTED_URL, params={**RANGE, **filters})
    assert response.status_code == 404


def test_counts_cases_per_machine_within_a_site(client, db, results):
    chrysalis = db.query(Machine).filter_by(name="chrysalis").one()
    # Same case identity on another machine at the same site is another case.
    other = Machine(
        name="improv",
        site_id=chrysalis.site_id,
        architecture="x86_64",
        scheduler="pbs",
    )
    db.add(other)
    db.flush()
    db.add(
        ExecutionDiscoveryResult(
            machine_id=other.id,
            case_identity="user/case-c",
            execution_id="7",
            outcome=INCOMPLETE,
            errors=[FILE_ERROR],
            created_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
        )
    )
    db.commit()

    group = _get(client, site_name=chrysalis.site)["groups"][0]
    assert (group["executions"], group["cases"]) == (3, 2)
    assert group["example"]["machine_name"] == "improv"


@pytest.mark.parametrize(
    "dates",
    [
        {},
        {"start_date": "2026-11-06", "end_date": "2026-11-05"},
        {"start_date": "2026-11-05", "end_date": "2026-11-05"},
        {"start_date": "2026-08-01", "end_date": "2026-11-05"},
    ],
)
def test_rejects_missing_or_invalid_date_ranges(client, reader, dates):
    assert client.get(REJECTED_URL, params=dates).status_code == 422


def test_returns_no_groups_without_rejections(client, reader):
    assert _get(client) == {"groups": [], "total": 0, "new_in_range": 0}
