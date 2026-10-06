"""Trusted source-directory submissions and duplicate-only ingestion."""

import pytest
from fastapi import HTTPException

from app.api.source_directories import record_source_directories
from app.features.catalog.models import SourceDirectory
from app.features.ingestion.api import _process_ingestion
from app.features.ingestion.enums import IngestionSourceType
from app.features.ingestion.ingest import IngestArchiveResult
from app.features.ingestion.schemas import SourceDirectoriesRequest
from app.features.user.models import UserRole
from tests.features.catalog.test_models import (
    _create_case,
    _create_dependencies,
    _create_execution,
)


def _owners(db):
    user, machine, ingestion = _create_dependencies(db)
    case = _create_case(db, machine=machine, name="same-case", hpc_username="alice")
    execution = _create_execution(
        db,
        case_id=case.id,
        ingestion_id=ingestion.id,
        user_id=user.id,
        execution_id="100.1-1",
    )
    return user, machine, case, execution


def _request(
    machine_name, *, username="alice", kind="staging", path="/performance/case"
):
    return SourceDirectoriesRequest(
        machine_name=machine_name,
        directories=[
            {
                "case_name": "same-case",
                "hpc_username": username,
                "execution_id": "100.1-1",
                "kind": kind,
                "case_path": path,
                "execution_path": f"{path}/100.1-1",
            }
        ],
    )


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SERVICE_ACCOUNT])
def test_source_directory_submission_is_idempotent_and_user_scoped(db, role):
    user, machine, case, execution = _owners(db)
    user.role = role
    other_case = _create_case(db, machine=machine, name="same-case", hpc_username="bob")
    _create_execution(
        db,
        case_id=other_case.id,
        ingestion_id=execution.ingestion_id,
        user_id=user.id,
        execution_id="100.1-1",
    )
    for kind, path in [
        ("staging", "/performance/case"),
        ("archive", "/archive/one/case"),
        ("archive", "/archive/two/case"),
    ]:
        payload = _request(machine.name, kind=kind, path=path)
        for _ in range(2):
            assert record_source_directories(payload, db, user).recorded_count == 1

    assert db.query(SourceDirectory).count() == 6
    assert not other_case.source_directories


def test_source_directory_submission_rejects_normal_user(db):
    user, machine, _, _ = _owners(db)
    user.role = UserRole.USER
    with pytest.raises(HTTPException) as exc:
        record_source_directories(_request(machine.name), db, user)
    assert exc.value.status_code == 403
    assert db.query(SourceDirectory).count() == 0


def test_source_directory_submission_rejects_unresolved_batch_without_partial_writes(
    db,
):
    user, machine, _, _ = _owners(db)
    user.role = UserRole.ADMIN
    db.commit()
    payload = _request(machine.name)
    payload.directories.append(
        _request(machine.name, username="missing").directories[0]
    )
    with pytest.raises(HTTPException) as exc:
        record_source_directories(payload, db, user)
    assert exc.value.status_code == 409
    assert db.query(SourceDirectory).count() == 0


def test_duplicate_only_ingestion_persists_explicit_paths(db):
    user, machine, _, _ = _owners(db)
    response = _process_ingestion(
        IngestArchiveResult(executions=[], created_count=0, duplicate_count=1),
        IngestionSourceType.HPC_UPLOAD,
        "/performance/case",
        machine.id,
        user,
        None,
        db,
        source_directories=_request(machine.name).directories,
    )
    assert response.created_count == 0
    assert response.duplicate_count == 1
    assert db.query(SourceDirectory).count() == 2


def test_missing_paths_do_not_insert_mappings(db):
    user, machine, _, _ = _owners(db)
    _process_ingestion(
        IngestArchiveResult(executions=[], created_count=0, duplicate_count=1),
        IngestionSourceType.HPC_UPLOAD,
        "/performance/case",
        machine.id,
        user,
        None,
        db,
    )
    assert db.query(SourceDirectory).count() == 0
