"""Rejected execution listing, authorization, filters, and limits."""

import pytest

from app.api import rejected_executions
from app.api.version import API_BASE
from app.features.ingestion.enums import ExecutionDiscoveryOutcome
from app.features.ingestion.models import ExecutionDiscoveryResult
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app

REJECTED_URL = f"{API_BASE}/ingestions/rejected-executions"
ERROR = {"field": "case_name", "code": "missing", "message": "case_name is required."}


@pytest.fixture
def reader(client, db, admin_user_sync):
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
    for machine_name, case_identity, execution_id, outcome, errors in [
        (
            "perlmutter",
            "user/case-b",
            "2",
            ExecutionDiscoveryOutcome.REJECTED_INVALID,
            [ERROR],
        ),
        (
            "perlmutter",
            "user/case-a",
            "1",
            ExecutionDiscoveryOutcome.REJECTED_INCOMPLETE,
            None,
        ),
        ("perlmutter", "user/case-a", "3", ExecutionDiscoveryOutcome.ACCEPTED, None),
        (
            "chrysalis",
            "user/case-c",
            "4",
            ExecutionDiscoveryOutcome.REJECTED_INVALID,
            [ERROR],
        ),
    ]:
        db.add(
            ExecutionDiscoveryResult(
                machine_id=machines[machine_name].id,
                case_identity=case_identity,
                execution_id=execution_id,
                outcome=outcome,
                errors=errors,
            )
        )
    db.commit()


def _rejected(machine_name, case_identity, execution_id, outcome, errors):
    return {
        "machine_name": machine_name,
        "case_identity": case_identity,
        "execution_id": execution_id,
        "outcome": outcome,
        "errors": errors,
    }


def test_rejected_executions_require_authentication(client):
    assert client.get(REJECTED_URL).status_code == 401


@pytest.mark.parametrize(
    "role,status_code",
    [(UserRole.USER, 403), (UserRole.ADMIN, 200), (UserRole.SERVICE_ACCOUNT, 200)],
)
def test_rejected_executions_require_ingestion_access(
    client, reader, role, status_code
):
    reader.role = role
    response = client.get(REJECTED_URL)
    assert response.status_code == status_code, response.text


def test_lists_only_current_rejections_in_order(client, db, results):
    response = client.get(REJECTED_URL)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "executions": [
            _rejected("chrysalis", "user/case-c", "4", "rejected_invalid", [ERROR]),
            _rejected("perlmutter", "user/case-a", "1", "rejected_incomplete", []),
            _rejected("perlmutter", "user/case-b", "2", "rejected_invalid", [ERROR]),
        ],
        "total": 3,
    }

    # Revalidation that accepts an execution removes it from the list.
    db.query(ExecutionDiscoveryResult).filter_by(
        execution_id="4"
    ).one().outcome = ExecutionDiscoveryOutcome.ACCEPTED
    db.commit()
    assert client.get(REJECTED_URL).json()["total"] == 2


@pytest.mark.parametrize(
    "filters,execution_ids",
    [
        ({"machine_name": "pm-cpu"}, ["1", "2"]),
        ({"site_name": "LCRC"}, ["4"]),
        ({"site_name": "nersc"}, ["1", "2"]),
        ({"site_name": "LCRC", "machine_name": "perlmutter"}, []),
    ],
)
def test_filters_by_machine_and_site(client, results, filters, execution_ids):
    body = client.get(REJECTED_URL, params=filters).json()
    assert [row["execution_id"] for row in body["executions"]] == execution_ids
    assert body["total"] == len(execution_ids)


@pytest.mark.parametrize("filters", [{"machine_name": "x"}, {"site_name": "x"}])
def test_rejects_unknown_machine_or_site(client, reader, filters):
    assert client.get(REJECTED_URL, params=filters).status_code == 404


def test_limits_rows_but_counts_all(client, results, monkeypatch):
    monkeypatch.setattr(rejected_executions, "REJECTED_EXECUTIONS_MAX", 2)
    body = client.get(REJECTED_URL).json()
    assert len(body["executions"]) == 2
    assert body["total"] == 3


def test_returns_empty_list_without_rejections(client, reader):
    assert client.get(REJECTED_URL).json() == {"executions": [], "total": 0}
