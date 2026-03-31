"""Tests for the ingestion API endpoints.

This test module provides comprehensive coverage for the ingestion API,
including path-based and upload-based ingestion endpoints.
"""

import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.ingestion.api import (
    _run_ingest_archive,
    _save_uploaded_file_and_hash,
    _set_reference_simulations,
    _validate_archive_path,
    _validate_upload_file,
    ingest_from_upload,
)
from app.features.ingestion.ingest import IngestArchiveResult
from app.features.ingestion.models import Ingestion
from app.features.ingestion.parsers.parser import ArchiveValidationError
from app.features.machine.models import Machine
from app.features.simulation.models import Case, Simulation
from app.features.simulation.schemas import SimulationCreate
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app


@pytest.fixture(autouse=True)
def override_auth_dependency(normal_user_sync):
    """Auto-login a test user for endpoints requiring authentication."""

    def fake_current_user():
        return User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.ADMIN,
        )

    app.dependency_overrides[current_active_user] = fake_current_user

    yield
    app.dependency_overrides.clear()


# Override dependency to simulate a non-admin user
def fake_non_admin_user():
    return User(
        id=1,
        email="user@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.USER,
    )


class TestIngestFromPathEndpoint:
    @staticmethod
    def _create_archive_file(
        tmp_path, name: str = "archive.tar.gz", content: bytes = b"x"
    ):
        archive_path = tmp_path / name
        archive_path.write_bytes(content)

        return archive_path

    def test_endpoint_returns_403_for_non_admin_user(
        self, client, db: Session, tmp_path
    ):
        """Test that non-admin users receive a 403 Forbidden response."""
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        app.dependency_overrides[current_active_user] = fake_non_admin_user

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        # Restore dependency overrides
        app.dependency_overrides.clear()

        assert res.status_code == 403
        assert (
            res.json()["detail"]
            == "Only administrators and service accounts may ingest from filesystem paths."
        )

    def test_endpoint_returns_summary(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = Case(name="test_case")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-summary-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0

    def test_endpoint_returns_409_on_conflict(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ValueError("Duplicate simulation"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 409
        assert res.json()["detail"] == "Duplicate simulation"

    def test_endpoint_includes_errors_in_response(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case1 = Case(name="test_case_errors")
        case2 = Case(name="case2_errors")
        db.add_all([case1, case2])
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case1.id),
                    "executionId": "exec-errors-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            ),
            SimulationCreate.model_validate(
                {
                    "caseId": str(case2.id),
                    "executionId": "exec-errors-2",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "def456",
                }
            ),
        ]
        mock_errors = [{"file": "sim2.json", "error": "Invalid format"}]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=2,
                duplicate_count=0,
                errors=mock_errors,
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        data = res.json()

        assert data["created_count"] == 2
        assert data["duplicate_count"] == 0
        assert data["errors"] == mock_errors

        assert len(data["simulations"]) == 2
        assert {simulation["execution_id"] for simulation in data["simulations"]} == {
            "exec-errors-1",
            "exec-errors-2",
        }
        assert {simulation["case_name"] for simulation in data["simulations"]} == {
            "test_case_errors",
            "case2_errors",
        }

    def test_endpoint_creates_audit_record(self, client, db: Session, tmp_path):
        """Test that ingestion creates an audit record in the database."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_content = b"audit-archive-content"
        archive_path = self._create_archive_file(
            tmp_path, "test.tar.gz", archive_content
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = Case(name="test_case_audit")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-audit-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            client.post(f"{API_BASE}/ingestions/from-path", json=payload)
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert str(ingestion.source_type) == "hpc_path"
        assert ingestion.status == "success"
        assert ingestion.created_count == 1
        assert ingestion.duplicate_count == 0
        assert ingestion.error_count == 0
        assert ingestion.archive_sha256 is None

    def test_endpoint_returns_400_when_archive_path_missing(
        self, client, db: Session, tmp_path
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        missing_path = tmp_path / "missing.tar.gz"
        payload = {"archive_path": str(missing_path), "machine_name": machine.name}

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert res.json()["detail"] == f"Archive path '{missing_path}' does not exist."

    def test_endpoint_returns_500_when_ingest_fails(
        self, client, db: Session, tmp_path
    ):
        """Test that a 500 is returned when archive processing fails."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "bad.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("processing failed"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 500
        assert "processing failed" in res.json()["detail"]

    def test_endpoint_returns_404_when_machine_not_found(self, client, tmp_path):
        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {
            "archive_path": str(archive_path),
            "machine_name": "does-not-exist-machine",
        }

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 404
        assert res.json()["detail"] == "Machine 'does-not-exist-machine' not found."

    @pytest.mark.parametrize("machine_alias", ["pm", "pm-cpu", "pm-gpu"])
    def test_endpoint_accepts_perlmutter_aliases(
        self, client, db: Session, tmp_path, machine_alias: str
    ):
        machine = db.query(Machine).filter(Machine.name == "perlmutter").first()
        if machine is None:
            machine = Machine(
                name="perlmutter",
                site="NERSC",
                architecture="AMD EPYC + NVIDIA A100",
                scheduler="slurm",
                gpu=True,
            )
            db.add(machine)
            db.commit()
            db.refresh(machine)

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine_alias}

        case = Case(name=f"test_case_alias_{machine_alias}")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": f"exec-{machine_alias}",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201


class TestIngestFromUploadEndpoint:
    @staticmethod
    def _create_archive_file(
        tmp_path, name: str = "archive.tar.gz", content: bytes = b"x"
    ):
        archive_path = tmp_path / name
        archive_path.write_bytes(content)

        return archive_path

    def test_upload_valid_zip_file(self, client, db: Session):
        """Test uploading a valid .zip archive."""
        machine = db.query(Machine).first()
        assert machine is not None

        # Create a mock file
        file_content = b"PK\x03\x04"  # ZIP file magic bytes
        file = BytesIO(file_content)

        case = Case(name="test_case_zip")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-zip-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test.zip", file, "application/zip")},
            )

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0
        assert len(data["simulations"]) == 1
        assert data["simulations"][0]["execution_id"] == "exec-zip-1"
        assert data["simulations"][0]["case_name"] == "test_case_zip"

    def test_upload_valid_tar_gz_file(self, client, db: Session):
        """Test uploading a valid .tar.gz archive."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"\x1f\x8b\x08"  # GZIP magic bytes
        file = BytesIO(file_content)

        case = Case(name="test_case_targz")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-targz-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test.tar.gz", file, "application/gzip")},
            )

        assert res.status_code == 201
        assert res.json()["simulations"][0]["execution_id"] == "exec-targz-1"

    def test_upload_invalid_file_extension(self, client, db: Session):
        """Test that invalid file extensions are rejected."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"some content"
        file = BytesIO(file_content)

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": machine.name},
            files={"file": ("test.txt", file, "text/plain")},
        )

        assert res.status_code == 400
        assert "File must be a .zip, .tar.gz, or .tgz archive" in res.json()["detail"]

    def test_upload_returns_404_when_machine_not_found(self, client):
        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": "does-not-exist-machine"},
            files={"file": ("test.zip", file, "application/zip")},
        )

        assert res.status_code == 404
        assert res.json()["detail"] == "Machine 'does-not-exist-machine' not found."

    def test_upload_creates_audit_record_with_sha256(self, client, db: Session):
        """Test that upload creates audit record with SHA256 hash."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04test content"
        file = BytesIO(file_content)

        case = Case(name="test_case_sha256")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-sha256-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_upload.zip", file, "application/zip")},
            )

        assert res.status_code == 201

        # Verify audit record with SHA256
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_upload.zip")
            .first()
        )

        assert ingestion is not None
        assert str(ingestion.source_type) == "browser_upload"
        assert ingestion.status == "success"
        assert ingestion.archive_sha256 is not None
        assert len(ingestion.archive_sha256) == 64  # SHA256 hex length

    def test_upload_rejects_partial_ingestion_results(self, client, db: Session):
        """Upload endpoint should fail instead of persisting partial ingestion results."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        case = Case(name="test_case_partial")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-partial-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]
        mock_errors = [{"file": "sim2.json", "error": "Invalid format"}]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=mock_errors,
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_partial.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": mock_errors,
        }

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_partial.zip")
            .first()
        )
        assert ingestion is None

    def test_upload_rejects_failed_ingestion_results(self, client, db: Session):
        """Upload endpoint should fail instead of persisting failed ingestion results."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing required field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[], created_count=0, duplicate_count=0, errors=mock_errors
            ),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("test_failed.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": mock_errors,
        }

        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_failed.zip")
            .first()
        )
        assert ingestion is None

    def test_upload_without_filename(self, client, db: Session):
        """Test that upload without filename is rejected."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        # Create a mock UploadFile with no filename
        mock_file = MagicMock()
        mock_file.filename = None
        mock_file.file = file

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            data={"machine_name": machine.name},
            files={"file": ("", file, "application/zip")},
        )

        # Should either reject or handle gracefully
        assert res.status_code in [400, 422]

    def test_path_endpoint_handles_lookup_error(self, client, db: Session, tmp_path):
        """Test that LookupError is handled with 400 response."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "lookup_error.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found"

    def test_path_endpoint_handles_generic_exception(
        self, client, db: Session, tmp_path
    ):
        """Test that generic exceptions are handled with 500 response."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "exception.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("Unexpected error"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 500
        assert res.json()["detail"] == "Unexpected error"

    def test_path_endpoint_failed_status_no_simulations_with_errors(
        self, client, db: Session, tmp_path
    ):
        """Test that failed status is set when no simulations are created but errors exist."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "failed_status.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=[], created_count=0, duplicate_count=0, errors=mock_errors
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        # Verify failed status in audit record
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert ingestion.status == "failed"
        assert ingestion.created_count == 0
        assert ingestion.error_count == 2

    def test_save_uploaded_file_rejects_large_files(self, tmp_path: Path):
        file_content = b"x" * (51 * 1024 * 1024)  # 51MB
        upload_file = UploadFile(file=BytesIO(file_content), filename="large_file.zip")

        with pytest.raises(HTTPException) as exc_info:
            _save_uploaded_file_and_hash(upload_file, tmp_path / "large_file.zip")

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "File too large"

    def test_upload_returns_structured_validation_errors(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None

        file = BytesIO(b"PK\x03\x04")
        validation_errors = [
            {
                "code": "missing_required_file",
                "execution_dir": "/tmp/archive/1.0-0",
                "file_spec": "env_case.xml..*.gz",
                "location": "casedocs/",
                "message": "Missing required 'env_case.xml..*.gz' in casedocs/ for '/tmp/archive/1.0-0'.",
            }
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ArchiveValidationError(validation_errors),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": ("invalid.zip", file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == {
            "message": "Archive validation failed.",
            "errors": validation_errors,
        }

    def test_upload_handles_lookup_error(self, client, db: Session):
        """Test that LookupError in upload is handled with 400 response."""

        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"lookup_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found in upload"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": (unique_filename, file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found in upload"

    def test_upload_handles_generic_exception(self, client, db: Session):
        """Test that generic exceptions in upload are handled with 500 response."""

        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"generic_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("Unexpected upload error"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                data={"machine_name": machine.name},
                files={"file": (unique_filename, file, "application/zip")},
            )

        assert res.status_code == 500
        assert res.json()["detail"] == "Unexpected upload error"

    def test_persist_simulations_with_artifacts(self, client, db: Session, tmp_path):
        """Test that simulations with artifacts are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_artifacts.tar.gz"
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = Case(name="test_case_artifacts")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-artifacts-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "artifacts": [
                        {
                            "kind": "output",
                            "uri": "https://example.com/output.tar.gz",
                            "description": "Model output",
                        }
                    ],
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert len(simulation.artifacts) == 1
        assert simulation.artifacts[0].kind == "output"
        assert simulation.artifacts[0].uri == "https://example.com/output.tar.gz"

    def test_persist_simulations_with_links(self, client, db: Session, tmp_path):
        """Test that simulations with external links are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "archive_with_links.tar.gz")
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = Case(name="test_case_links")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-links-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "links": [
                        {
                            "kind": "diagnostic",
                            "url": "https://example.com/diagnostics",
                            "label": "Diagnostics Dashboard",
                        }
                    ],
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert len(simulation.links) == 1
        assert simulation.links[0].kind == "diagnostic"
        assert simulation.links[0].url == "https://example.com/diagnostics"

    def test_upload_with_none_filename_in_validation(self, client):
        """Test that upload with file.filename = None is rejected by validation."""

        file_content = b"PK\x03\x04"
        file_obj = BytesIO(file_content)

        # Create a real UploadFile with filename = None
        upload_file = UploadFile(file=file_obj, filename=None)

        with pytest.raises(HTTPException) as exc_info:
            _validate_upload_file(upload_file)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Filename is required"

    def test_persist_simulations_with_git_repository_url(
        self, client, db: Session, tmp_path
    ):
        """Test that simulations with git_repository_url are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_git_url.tar.gz"
        )
        payload = {"archive_path": str(archive_path), "machine_name": machine.name}

        case = Case(name="test_case_git_url")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-git-url-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                    "gitRepositoryUrl": "https://github.com/E3SM-Project/E3SM.git",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert (
            simulation.git_repository_url == "https://github.com/E3SM-Project/E3SM.git"
        )

    def test_persist_simulations_with_hpc_username(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(
            tmp_path, "archive_with_hpc_username.tar.gz"
        )
        payload = {
            "archive_path": str(archive_path),
            "machine_name": machine.name,
            "hpc_username": "nersc-user",
        }

        case = Case(name="test_case_hpc_username")
        db.add(case)
        db.flush()

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "caseId": str(case.id),
                    "executionId": "exec-hpc-username-1",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "experimental",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            )
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=IngestArchiveResult(
                simulations=mock_simulations,
                created_count=1,
                duplicate_count=0,
                errors=[],
            ),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = db.query(Simulation).filter(Simulation.case_id == case.id).first()

        assert simulation is not None
        assert simulation.hpc_username == "nersc-user"


class TestIngestionApiCoverage:
    def test_set_reference_simulations_skips_non_uuid_case_id(self):
        """Covers defensive skip when a created simulation has a non-UUID case_id."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = []

        sim = Simulation(case_id="not-a-uuid", id=uuid.uuid4())

        _set_reference_simulations(db, [sim])

        db.add.assert_not_called()

    def test_run_ingest_archive_handles_validation_error(self, db: Session):
        """Covers ValidationError branch in _run_ingest_archive."""

        class _InvalidSchema(BaseModel):
            value: int

        with pytest.raises(ValidationError) as validation_exc:
            _InvalidSchema.model_validate({"value": "not-an-int"})

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=validation_exc.value,
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run_ingest_archive("/tmp/archive.tar.gz", "/tmp", db)

        assert exc_info.value.status_code == 400

    def test_run_ingest_archive_handles_archive_validation_error(self, db: Session):
        validation_errors = [
            {
                "code": "missing_required_file",
                "execution_dir": "/tmp/archive/1.0-0",
                "file_spec": "CaseStatus..*.gz",
                "location": "archive root",
                "message": "Missing required 'CaseStatus..*.gz' in archive root for '/tmp/archive/1.0-0'.",
            }
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=ArchiveValidationError(validation_errors),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _run_ingest_archive("/tmp/archive.tar.gz", "/tmp", db)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == {
            "message": "Archive validation failed.",
            "errors": validation_errors,
        }

    def test_ingest_from_upload_defensive_filename_none_branch(
        self, db: Session, normal_user_sync: dict
    ):
        """Covers defensive filename None branch in ingest_from_upload."""
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        upload_file = UploadFile(file=BytesIO(b"archive-bytes"), filename=None)

        with patch(
            "app.features.ingestion.api._validate_upload_file", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                ingest_from_upload(
                    file=upload_file,
                    machine_name=machine.name,
                    db=db,
                    user=user,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Filename is required"

    def test_ingest_from_upload_ignores_file_close_errors(
        self, db: Session, normal_user_sync: dict
    ):
        machine = db.query(Machine).first()
        assert machine is not None

        user = User(
            id=normal_user_sync["id"],
            email=normal_user_sync["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        raw_file = MagicMock()
        raw_file.close.side_effect = RuntimeError("close failed")
        upload_file = UploadFile(file=raw_file, filename="archive.zip")
        response = MagicMock()

        with (
            patch(
                "app.features.ingestion.api._validate_upload_file", return_value=None
            ),
            patch(
                "app.features.ingestion.api._save_uploaded_file_and_hash",
                return_value="deadbeef",
            ),
            patch(
                "app.features.ingestion.api._run_ingest_archive",
                return_value=IngestArchiveResult(
                    simulations=[],
                    created_count=0,
                    duplicate_count=0,
                    errors=[],
                ),
            ),
            patch(
                "app.features.ingestion.api._process_ingestion",
                return_value=response,
            ),
        ):
            result = ingest_from_upload(
                file=upload_file,
                machine_name=machine.name,
                db=db,
                user=user,
            )

        assert result is response
        raw_file.close.assert_called_once_with()

    def test_validate_archive_path_not_file_or_dir(self, tmp_path):
        """Covers the branch where path exists but is neither file nor dir."""
        archive_path = tmp_path / "special"
        archive_path.touch()

        with (
            patch.object(Path, "is_file", return_value=False),
            patch.object(Path, "is_dir", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _validate_archive_path(archive_path)

        assert exc_info.value.status_code == 400
        assert "must be a file or directory" in exc_info.value.detail
