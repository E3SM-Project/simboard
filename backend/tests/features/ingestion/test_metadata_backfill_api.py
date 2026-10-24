"""Database-backed metadata selection, ownership, and update contracts."""

import pytest
from fastapi import HTTPException

from app.api.metadata_backfill import backfill_record, list_records
from app.features.catalog.enums import ArtifactKind
from app.features.catalog.models import Artifact, MetadataChange
from app.features.ingestion.metadata_backfill import MetadataUpdate, stored_values
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


@pytest.mark.parametrize("alias", [None, "arcticx4"])
def test_grid_repair_pair_dry_run_apply_and_repeat(db, alias):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.grid_alias = "wrong-alias"
    execution.grid_long_name = "wrong-spec"
    db.commit()
    request = MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["grid"],
        values={"grid_long_name": "a%arcticx4_l%r05", "grid_alias": alias},
        expected={"grid_long_name": "wrong-spec", "grid_alias": "wrong-alias"},
    )
    assert backfill_record(request, db, user)["outcome"] == "unchanged"
    request.overwrite = True
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.grid_long_name == "wrong-spec"
    request.dry_run = False
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.grid_long_name == "a%arcticx4_l%r05"
    assert execution.grid_alias == alias
    assert backfill_record(request, db, user)["outcome"] == "unchanged"
    changes = {row.field_name: row.new_value for row in db.query(MetadataChange).all()}
    assert changes["grid_alias"] == alias
    assert changes["grid_long_name"] == "a%arcticx4_l%r05"


def test_grid_repair_checks_unchanged_pair_member(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    request = MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["grid"],
        values={"grid_long_name": "new-spec", "grid_alias": None},
        expected=stored_values(execution),
        overwrite=True,
        dry_run=False,
    )
    execution.grid_alias = "concurrent-change"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        backfill_record(request, db, user)

    assert exc.value.status_code == 409
    db.refresh(execution)
    assert execution.grid_long_name != "new-spec"


@pytest.mark.parametrize(
    "values",
    [
        {"grid_alias": None},
        {"grid_long_name": "spec"},
        {"grid_long_name": None, "grid_alias": None},
        {"grid_long_name": "   ", "grid_alias": None},
    ],
)
def test_grid_repair_requires_explicit_valid_pair(db, values):
    _, machine, case, execution = _owners(db)
    with pytest.raises(ValueError, match="grid"):
        MetadataUpdate(
            machine_name=machine.name,
            record_id=execution.id,
            case_name=case.name,
            hpc_username=case.hpc_username,
            execution_id=execution.execution_id,
            fields=["grid"],
            values=values,
            expected=stored_values(execution),
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


def test_backfill_preserves_year_zero_dates_and_history(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    request = _payload(machine, case, execution, overwrite=True, dry_run=False)
    request.values.simulation_start_date = "0000-01-02"
    request.values.simulation_end_date = "0000-12-31"
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.simulation_start_date == "0000-01-02"
    assert execution.simulation_end_date == "0000-12-31"
    changes = {row.field_name: row.new_value for row in db.query(MetadataChange).all()}
    assert changes["simulation_start_date"] == "0000-01-02"
    assert changes["simulation_end_date"] == "0000-12-31"


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
    execution.simulation_start_date = "1850-01-01"
    db.commit()

    request = _payload(machine, case, execution, overwrite=True)
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.simulation_start_date == "1850-01-01"
    assert db.query(MetadataChange).count() == 0

    request.dry_run = False
    request.expected.simulation_start_date = "1900-01-01"

    with pytest.raises(HTTPException) as exc:
        backfill_record(request, db, user)
    assert exc.value.status_code == 409

    db.refresh(execution)
    assert execution.simulation_start_date == "1850-01-01"


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


@pytest.mark.parametrize("existing_script", [False, True])
def test_apply_records_execution_history_in_same_transaction(db, existing_script):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.simulation_start_date = "1850-01-01"
    execution.simulation_end_date = "1851-01-01"
    if existing_script:
        execution.artifacts.append(
            Artifact(kind=ArtifactKind.RUN_SCRIPT, uri="/old/run.sh")
        )
    db.commit()
    request = MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["simulation-dates", "run-script"],
        values={
            "simulation_start_date": "2020-01-01",
            "simulation_end_date": "2021-01-01",
            "run_script": "/new/run.sh",
        },
        expected={
            "simulation_start_date": "1850-01-01",
            "simulation_end_date": "1851-01-01",
            "run_script": "/old/run.sh" if existing_script else None,
        },
        overwrite=True,
    )
    assert backfill_record(request, db, user)["outcome"] == "changed"
    assert db.query(MetadataChange).count() == 0

    request.dry_run = False
    assert backfill_record(request, db, user)["outcome"] == "changed"
    history = (
        db.query(MetadataChange).filter(MetadataChange.entity_id == execution.id).all()
    )
    assert {change.field_name for change in history} == {
        "simulation_start_date",
        "simulation_end_date",
        "artifacts",
    }
    assert all(
        change.entity_type == "execution"
        and change.editor_id == user.id
        and change.reason == "Metadata backfill"
        for change in history
    )
    dates = next(
        change for change in history if change.field_name == "simulation_start_date"
    )
    assert (dates.old_value, dates.new_value) == ("1850-01-01", "2020-01-01")
    scripts = next(change for change in history if change.field_name == "artifacts")
    assert scripts.new_value[0]["uri"] == "/new/run.sh"
    assert (scripts.old_value[0]["uri"] if existing_script else scripts.old_value) == (
        "/old/run.sh" if existing_script else []
    )
    assert backfill_record(request, db, user)["outcome"] == "unchanged"
    assert db.query(MetadataChange).count() == 3


def test_failed_commit_rolls_back_metadata_and_history(db, monkeypatch):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.simulation_start_date = "1850-01-01"
    db.commit()
    request = _payload(machine, case, execution, overwrite=True, dry_run=False)

    def fail_commit():
        db.flush()
        raise RuntimeError("Simulated failure before commit")

    with monkeypatch.context() as patch:
        patch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="Simulated failure"):
            backfill_record(request, db, user)

    db.refresh(execution)
    assert execution.simulation_start_date == "1850-01-01"
    assert db.query(MetadataChange).count() == 0


@pytest.mark.parametrize("alias", ["F20TR-GHG", None])
@pytest.mark.parametrize("old_long_name", ["AQUAPLANET", ""])
def test_component_set_repair_is_guarded_and_idempotent(db, alias, old_long_name):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    execution.compset_long_name = old_long_name
    db.commit()
    before = stored_values(execution).model_dump()
    original_dates = (execution.simulation_start_date, execution.simulation_end_date)
    request = MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["component-set"],
        values={
            "compset_long_name": "1850_EAM_ELM_" + "X" * 121,
            "compset_alias": alias,
        },
        expected=before,
        overwrite=True,
    )
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert stored_values(execution).model_dump() == before
    assert db.query(MetadataChange).count() == 0

    request.dry_run = False
    assert backfill_record(request, db, user)["outcome"] == "changed"
    db.refresh(execution)
    assert execution.compset_long_name == request.values.compset_long_name
    assert execution.compset_alias == alias
    assert (
        execution.simulation_start_date,
        execution.simulation_end_date,
    ) == original_dates
    assert {row.field_name for row in db.query(MetadataChange).all()} == {
        "compset_long_name",
        "compset_alias",
    }
    assert backfill_record(request, db, user)["outcome"] == "unchanged"
    assert db.query(MetadataChange).count() == 2


def test_component_set_repair_rejects_stale_pair_and_requires_overwrite(db):
    user, machine, case, execution = _owners(db)
    user.role = UserRole.ADMIN
    db.commit()
    before = stored_values(execution).model_dump()
    request = MetadataUpdate(
        machine_name=machine.name,
        record_id=execution.id,
        case_name=case.name,
        hpc_username=case.hpc_username,
        execution_id=execution.execution_id,
        fields=["component-set"],
        values={"compset_long_name": "1850_EAM_ELM", "compset_alias": None},
        expected=before,
        dry_run=False,
    )
    assert backfill_record(request, db, user)["outcome"] == "unchanged"
    request.overwrite = True
    execution.compset_long_name = "concurrent-change"
    db.commit()
    with pytest.raises(HTTPException) as exc:
        backfill_record(request, db, user)
    assert exc.value.status_code == 409
    db.refresh(execution)
    assert execution.compset_alias == before["compset_alias"]
    assert db.query(MetadataChange).count() == 0


@pytest.mark.parametrize(
    "section,field",
    [
        ("values", "compset_long_name"),
        ("values", "compset_alias"),
        ("expected", "compset_alias"),
    ],
)
def test_component_repair_requires_explicit_pair(section, field):
    pair = {"compset_long_name": "1850_EAM_ELM", "compset_alias": None}
    payload = {"values": dict(pair), "expected": dict(pair)}
    del payload[section][field]
    with pytest.raises(ValueError, match="Explicit component-set pair"):
        MetadataUpdate(
            machine_name="chrysalis",
            record_id="00000000-0000-0000-0000-000000000001",
            case_name="case",
            hpc_username="alice",
            execution_id="1.1-1",
            fields=["component-set"],
            **payload,
        )
