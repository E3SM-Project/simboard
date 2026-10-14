"""Database-backed metadata selection, ownership, and update contracts."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.api.metadata_backfill import backfill_record, list_records
from app.features.catalog.enums import ArtifactKind
from app.features.catalog.models import Artifact
from app.features.ingestion.metadata_backfill import MetadataUpdate
from app.features.user.models import UserRole
from tests.features.ingestion.test_source_directory_api import _owners


def _payload(machine, case, execution, **kwargs):
    return MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["simulation-dates"],
        values={"simulation_start_date": "2020-01-01"},
        expected={"simulation_start_date": execution.simulation_start_date},
        **kwargs,
    )


@pytest.mark.parametrize("operation", ["read", "write"])
def test_backfill_rejects_normal_user(db, operation):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.USER

    with pytest.raises(HTTPException) as exc:
        if operation == "read":
            list_records(machine.name, db, user, offset=0, limit=100)
        else:
            backfill_record(_payload(machine, case, execution), db, user)

    assert exc.value.status_code == 403


def test_selection_filters_and_pagination(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN

    records = list_records(
        machine.name,
        db,
        user,
        case_name=case.name,
        hpc_username=case.hpc_username,
        offset=0,
        limit=1,
    )["records"]

    assert [r["record_id"] for r in records] == [str(execution.id)]
    assert (
        list_records(machine.name, db, user, case_name="other", offset=0, limit=100)[
            "records"
        ]
        == []
    )
    assert list_records(machine.name, db, user, offset=1, limit=1)["records"] == []


@pytest.mark.parametrize(
    "field", ["case_name", "hpc_username", "execution_id", "machine_name"]
)
def test_update_requires_complete_identity(db, field):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    request = _payload(machine, case, execution)
    setattr(request, field, "wrong")

    with pytest.raises(HTTPException) as exc:
        backfill_record(request, db, user)

    assert exc.value.status_code == 404


def test_dry_run_and_stale_update_do_not_write(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.simulation_start_date = date(1850, 1, 1)
    db.commit()

    request = _payload(machine, case, execution, overwrite=True)
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.simulation_start_date == date(1850, 1, 1)

    request.dry_run = False
    request.expected.simulation_start_date = date(1900, 1, 1)

    with pytest.raises(HTTPException) as exc:
        backfill_record(request, db, user)
    assert exc.value.status_code == 409

    db.refresh(execution)
    assert execution.simulation_start_date == date(1850, 1, 1)


def test_multiple_run_scripts_are_reported_and_not_overwritten(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.artifacts = [
        Artifact(kind=ArtifactKind.RUN_SCRIPT, uri="/one"),
        Artifact(kind=ArtifactKind.RUN_SCRIPT, uri="/two"),
    ]
    db.commit()

    assert list_records(machine.name, db, user, offset=0, limit=100)["records"][0][
        "error"
    ]

    with pytest.raises(HTTPException) as exc:
        backfill_record(_payload(machine, case, execution), db, user)

    assert exc.value.status_code == 409
