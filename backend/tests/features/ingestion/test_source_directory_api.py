"""Trusted source-directory submissions and duplicate-only ingestion."""

import pytest
from fastapi import HTTPException

from app.api.source_directories import record_source_directories
from app.features.catalog.models import SourceDirectory
from app.features.catalog.source_directories import select_performance_source_directory
from app.features.ingestion.api import _process_ingestion
from app.features.ingestion.enums import IngestionSourceType
from app.features.ingestion.ingest import IngestArchiveResult
from app.features.ingestion.schemas import SourceDirectoriesRequest
from app.features.user.models import UserRole
from tests.features.catalog.test_models import (
    _create_case,
    _create_dependencies,
    _create_execution,
    _create_machine,
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


def test_source_directory_submission_reports_missing_owners_without_guessing(
    db,
):
    user, machine, _, _ = _owners(db)
    user.role = UserRole.ADMIN
    db.commit()
    payload = _request(machine.name)
    payload.directories.append(
        _request(machine.name, username="missing").directories[0]
    )
    response = record_source_directories(payload, db, user)
    assert response.recorded_count == 1
    assert response.unresolved == payload.directories[1:]
    assert db.query(SourceDirectory).count() == 2


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


def test_staging_to_archive_then_late_staging_keeps_archive(db):
    user, machine, case, execution = _owners(db)
    for kind, path, expected_path in [
        ("staging", "/staging/case", "/staging/case"),
        ("archive", "/archive/case", "/archive/case"),
        ("staging", "/staging/another/case", "/archive/case"),
    ]:
        response = _process_ingestion(
            IngestArchiveResult(executions=[], created_count=0, duplicate_count=1),
            IngestionSourceType.HPC_UPLOAD,
            path,
            machine.id,
            user,
            None,
            db,
            source_directories=_request(machine.name, kind=kind, path=path).directories,
        )
        assert response.duplicate_count == 1
        db.expire_all()
        for owner, suffix in [(case, ""), (execution, "/100.1-1")]:
            selected = select_performance_source_directory(owner.source_directories)
            assert selected is not None
            assert selected.path == expected_path + suffix

    assert db.query(SourceDirectory).count() == 6


def test_source_directory_http_validation_and_response(db, client, monkeypatch):
    from app.api.version import API_BASE
    from app.features.user.manager import current_active_user
    from app.main import app

    user, machine, _, _ = _owners(db)
    user.role = UserRole.SERVICE_ACCOUNT
    monkeypatch.setitem(app.dependency_overrides, current_active_user, lambda: user)
    payload = _request(machine.name).model_dump(mode="json")
    response = client.post(f"{API_BASE}/ingestions/source-directories", json=payload)
    assert response.status_code == 200
    assert response.json() == {"recorded_count": 1, "unresolved": []}

    payload["directories"][0]["execution_path"] = "relative/path"
    assert (
        client.post(
            f"{API_BASE}/ingestions/source-directories", json=payload
        ).status_code
        == 422
    )


def test_source_directory_submission_does_not_cross_machines(db):
    user, _, _, _ = _owners(db)
    user.role = UserRole.ADMIN
    other_machine = _create_machine(db)
    response = record_source_directories(_request(other_machine.name), db, user)
    assert response.recorded_count == 0
    assert len(response.unresolved) == 1
    assert db.query(SourceDirectory).count() == 0


def test_explicit_ingestion_mapping_failure_rolls_back_audit(db):
    from app.features.ingestion.models import Ingestion

    user, machine, _, _ = _owners(db)
    db.commit()
    initial_count = db.query(Ingestion).count()
    with pytest.raises(HTTPException) as exc:
        _process_ingestion(
            IngestArchiveResult(executions=[], created_count=0, duplicate_count=1),
            IngestionSourceType.HPC_UPLOAD,
            "/performance/case",
            machine.id,
            user,
            None,
            db,
            source_directories=_request(machine.name, username="missing").directories,
        )
    assert exc.value.status_code == 409
    assert db.query(Ingestion).count() == initial_count
    assert db.query(SourceDirectory).count() == 0


@pytest.mark.parametrize("endpoint", ["from-path", "from-hpc-upload"])
def test_ingestion_endpoints_accept_explicit_directory_payloads(
    db, client, monkeypatch, endpoint, tmp_path
):
    import json

    from app.api.version import API_BASE
    from app.features.ingestion import api
    from app.features.user.manager import current_active_user
    from app.main import app

    user, machine, _, _ = _owners(db)
    user.role = UserRole.SERVICE_ACCOUNT
    monkeypatch.setitem(app.dependency_overrides, current_active_user, lambda: user)
    monkeypatch.setattr(
        api,
        "_run_ingest_archive",
        lambda **kwargs: IngestArchiveResult(
            executions=[],
            created_count=0,
            duplicate_count=1,
        ),
    )
    directories = _request(machine.name).model_dump(mode="json")["directories"]
    if endpoint == "from-path":
        response = client.post(
            f"{API_BASE}/ingestions/{endpoint}",
            json={
                "archive_path": str(tmp_path),
                "machine_name": machine.name,
                "source_directories": directories,
            },
        )
    else:
        response = client.post(
            f"{API_BASE}/ingestions/{endpoint}",
            data={
                "machine_name": machine.name,
                "case_path": "/performance/case",
                "processed_execution_ids": "100.1-1",
                "source_directories": json.dumps(directories),
            },
            files={"file": ("case.tar.gz", b"archive")},
        )
    assert response.status_code == 201
    assert response.json()["duplicate_count"] == 1
    assert db.query(SourceDirectory).count() == 2

    if endpoint == "from-hpc-upload":
        invalid_response = client.post(
            f"{API_BASE}/ingestions/{endpoint}",
            data={
                "machine_name": machine.name,
                "case_path": "/performance/case",
                "processed_execution_ids": "100.1-1",
                "source_directories": "not-json",
            },
            files={"file": ("case.tar.gz", b"archive")},
        )
        assert invalid_response.status_code == 422
