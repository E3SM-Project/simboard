from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.catalog.models import DiagnosticProvenanceState, ExternalLink
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app
from tests.features.catalog.test_api import (
    _create_matching_execution,
    _create_service_account_token,
    use_real_auth,
)


def _payload(*, case_name: str, machine: str, path: str) -> dict:
    return {
        "caseName": case_name,
        "machine": machine,
        "hpcUsername": "scanner-user",
        "diagnostics": [
            {
                "name": "zppy diagnostics",
                "url": "https://diagnostics.example.org/archive/case",
                "kind": "diagnostic",
            }
        ],
        "provenance": {
            "archiveRelativeCasePath": path,
            "settingsFilename": "provenance.20260811_120000_000000.settings",
            "provenanceTimestamp": "2026-08-11T12:00:00Z",
            "fingerprint": "a" * 64,
        },
    }


def _matching_case(db: Session):
    machine = db.query(Machine).first()
    assert machine is not None
    user, token = _create_service_account_token(db)
    case, _ = _create_matching_execution(
        db,
        case_name=f"scanner-state-{uuid4()}",
        machine_id=machine.id,
        machine_name=machine.name,
        user_id=user.id,
        execution_id=f"scanner-{uuid4()}",
        hpc_username="scanner-user",
        source_reference=f"scanner-state-{uuid4()}",
    )
    return machine, user, token, case


@use_real_auth
def test_scanner_link_is_idempotent_and_state_is_readable(client, db: Session) -> None:
    machine, _, token, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine=machine.name, path="production/e3sm/case"
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert (
        client.post(
            f"{API_BASE}/diagnostics/scanner/link", json=payload, headers=headers
        ).status_code
        == 204
    )
    assert (
        client.post(
            f"{API_BASE}/diagnostics/scanner/link", json=payload, headers=headers
        ).status_code
        == 204
    )

    state = db.query(DiagnosticProvenanceState).one()
    assert state.machine_name == machine.name
    assert state.settings_filename == payload["provenance"]["settingsFilename"]
    assert db.query(ExternalLink).filter(ExternalLink.case_id == case.id).count() == 1

    response = client.get(
        f"{API_BASE}/diagnostics/scanner-state",
        params={
            "machine": machine.name,
            "archive_relative_case_path": "production/e3sm/case",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["fingerprint"] == "a" * 64


@use_real_auth
def test_scanner_state_returns_404_for_unknown_machine(client, db: Session) -> None:
    _, _, token, _ = _matching_case(db)

    response = client.get(
        f"{API_BASE}/diagnostics/scanner-state",
        params={
            "machine": "unknown-machine",
            "archive_relative_case_path": "production/e3sm/case",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown machine."


@use_real_auth
def test_scanner_link_rejects_multiple_diagnostics(client, db: Session) -> None:
    machine, _, token, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine=machine.name, path="production/e3sm/case"
    )
    payload["diagnostics"].append(payload["diagnostics"][0].copy())

    response = client.post(
        f"{API_BASE}/diagnostics/scanner/link",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Scanner payload requires one diagnostic."


@use_real_auth
def test_scanner_link_rejects_unsafe_archive_path(client, db: Session) -> None:
    machine, _, token, case = _matching_case(db)
    payload = _payload(case_name=case.name, machine=machine.name, path="../outside")

    response = client.post(
        f"{API_BASE}/diagnostics/scanner/link",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid archive-relative case path."


@use_real_auth
def test_scanner_link_returns_404_for_unknown_machine(client, db: Session) -> None:
    _, _, token, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine="unknown-machine", path="production/e3sm/case"
    )

    response = client.post(
        f"{API_BASE}/diagnostics/scanner/link",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No matching case found."


@use_real_auth
def test_scanner_endpoints_reject_regular_user(client, db: Session) -> None:
    machine, _, _, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine=machine.name, path="production/e3sm/case"
    )
    regular_user = User(
        id=uuid4(),
        email="regular-scanner-user@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.USER,
    )
    app.dependency_overrides[current_active_user] = lambda: regular_user
    try:
        response = client.post(f"{API_BASE}/diagnostics/scanner/link", json=payload)
    finally:
        app.dependency_overrides.pop(current_active_user, None)

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Scanner access requires an administrator or service account."
    )


@use_real_auth
def test_scanner_link_rolls_back_link_when_state_write_fails(
    client, db: Session
) -> None:
    machine, service_user, _, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine=machine.name, path="production/e3sm/fail"
    )
    original_execute = db.execute

    def fail_only_state_insert(statement, *args, **kwargs):
        table = getattr(statement, "table", None)
        if table is not None and table.name == "diagnostic_provenance_states":
            raise RuntimeError("state failure")
        return original_execute(statement, *args, **kwargs)

    app.dependency_overrides[current_active_user] = lambda: service_user
    try:
        with patch.object(db, "execute", side_effect=fail_only_state_insert):
            with TestClient(app, raise_server_exceptions=False) as error_client:
                response = error_client.post(
                    f"{API_BASE}/diagnostics/scanner/link", json=payload
                )
    finally:
        app.dependency_overrides.pop(current_active_user, None)

    assert response.status_code == 500
    assert db.query(ExternalLink).filter(ExternalLink.case_id == case.id).count() == 0


@use_real_auth
def test_deleting_scanner_link_cascades_provenance_state(client, db: Session) -> None:
    machine, _, token, case = _matching_case(db)
    payload = _payload(
        case_name=case.name, machine=machine.name, path="development/e3sm/case"
    )
    assert (
        client.post(
            f"{API_BASE}/diagnostics/scanner/link",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 204
    )

    link = db.query(ExternalLink).filter(ExternalLink.case_id == case.id).one()
    db.delete(link)
    db.commit()
    assert db.query(DiagnosticProvenanceState).count() == 0
