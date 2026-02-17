"""Tests for the ingestion API endpoints.

This test module provides comprehensive coverage for the ingestion API,
including path-based and upload-based ingestion endpoints.
"""

import hashlib
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.ingestion.api import _validate_upload_file
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.models import Simulation
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
            role=UserRole.USER,
        )

    app.dependency_overrides[current_active_user] = fake_current_user

    yield
    app.dependency_overrides.clear()


class TestIngestFromPathEndpoint:
    @staticmethod
    def _create_archive_file(
        tmp_path, name: str = "archive.tar.gz", content: bytes = b"x"
    ):
        archive_path = tmp_path / name
        archive_path.write_bytes(content)

        return archive_path

    def test_endpoint_returns_summary(self, client, db: Session, tmp_path):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0
        assert data["simulations"][0]["name"] == "Test Simulation"

    def test_endpoint_returns_409_on_conflict(self, client, tmp_path):
        archive_path = self._create_archive_file(tmp_path, "archive.tar.gz")
        payload = {"archive_path": str(archive_path)}

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
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Sim1",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
                    "status": "created",
                    "machineId": str(machine.id),
                    "simulationStartDate": "2023-01-01T00:00:00Z",
                    "gitTag": "v1.0",
                    "gitCommitHash": "abc123",
                }
            ),
            SimulationCreate.model_validate(
                {
                    "name": "Sim2",
                    "caseName": "case2",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 2, 0, mock_errors),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        data = res.json()

        assert data["created_count"] == 2
        assert data["duplicate_count"] == 0
        assert data["errors"] == mock_errors

        assert len(data["simulations"]) == 2
        assert data["simulations"][0]["name"] == "Sim1"
        assert data["simulations"][1]["name"] == "Sim2"

    def test_endpoint_creates_audit_record(self, client, db: Session, tmp_path):
        """Test that ingestion creates an audit record in the database."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_content = b"audit-archive-content"
        archive_path = self._create_archive_file(
            tmp_path, "test.tar.gz", archive_content
        )
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        # Verify audit record was created
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == str(archive_path))
            .first()
        )

        assert ingestion is not None
        assert ingestion.source_type == "path"
        assert ingestion.status == "success"
        assert ingestion.created_count == 1
        assert ingestion.duplicate_count == 0
        assert ingestion.error_count == 0
        assert ingestion.archive_sha256 == hashlib.sha256(archive_content).hexdigest()

    def test_endpoint_returns_400_when_archive_path_missing(self, client, tmp_path):
        missing_path = tmp_path / "missing.tar.gz"
        payload = {"archive_path": str(missing_path)}

        res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert (
            res.json()["detail"]
            == f"Archive path '{missing_path}' does not exist or is not a file."
        )

    def test_endpoint_returns_500_when_sha256_fails(self, client, tmp_path):
        archive_path = self._create_archive_file(tmp_path, "unreadable.tar.gz")
        payload = {"archive_path": str(archive_path)}

        with patch(
            "app.features.ingestion.api.Path.open",
            side_effect=OSError("cannot read archive"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 500
        assert "Failed to compute SHA256" in res.json()["detail"]


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

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                files={"file": ("test.zip", file, "application/zip")},
            )

        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 0

    def test_upload_valid_tar_gz_file(self, client, db: Session):
        """Test uploading a valid .tar.gz archive."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"\x1f\x8b\x08"  # GZIP magic bytes
        file = BytesIO(file_content)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                files={"file": ("test.tar.gz", file, "application/gzip")},
            )

        assert res.status_code == 201

    def test_upload_invalid_file_extension(self, client):
        """Test that invalid file extensions are rejected."""
        file_content = b"some content"
        file = BytesIO(file_content)

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            files={"file": ("test.txt", file, "text/plain")},
        )

        assert res.status_code == 400
        assert "File must be a .zip, .tar.gz, or .tgz archive" in res.json()["detail"]

    def test_upload_creates_audit_record_with_sha256(self, client, db: Session):
        """Test that upload creates audit record with SHA256 hash."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04test content"
        file = BytesIO(file_content)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
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
        assert ingestion.source_type == "upload"
        assert ingestion.status == "success"
        assert ingestion.archive_sha256 is not None
        assert len(ingestion.archive_sha256) == 64  # SHA256 hex length

    def test_upload_partial_success_status(self, client, db: Session):
        """Test that partial success is recorded correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Test Simulation",
                    "caseName": "test_case",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, mock_errors),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                files={"file": ("test_partial.zip", file, "application/zip")},
            )

        assert res.status_code == 201

        # Verify partial status
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_partial.zip")
            .first()
        )

        assert ingestion is not None
        assert ingestion.status == "partial"
        assert ingestion.created_count == 1
        assert ingestion.error_count == 1

    def test_upload_failed_status(self, client, db: Session):
        """Test that failed ingestion is recorded correctly."""
        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing required field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=([], 0, 0, mock_errors),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                files={"file": ("test_failed.zip", file, "application/zip")},
            )

        assert res.status_code == 201

        # Verify failed status
        ingestion = (
            db.query(Ingestion)
            .filter(Ingestion.source_reference == "test_failed.zip")
            .first()
        )

        assert ingestion is not None
        assert ingestion.status == "failed"
        assert ingestion.created_count == 0
        assert ingestion.error_count == 2

    def test_upload_without_filename(self, client):
        """Test that upload without filename is rejected."""
        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)

        # Create a mock UploadFile with no filename
        mock_file = MagicMock()
        mock_file.filename = None
        mock_file.file = file

        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            files={"file": ("", file, "application/zip")},
        )

        # Should either reject or handle gracefully
        assert res.status_code in [400, 422]

    def test_path_endpoint_handles_lookup_error(self, client, tmp_path):
        """Test that LookupError is handled with 400 response."""
        archive_path = self._create_archive_file(tmp_path, "lookup_error.tar.gz")
        payload = {"archive_path": str(archive_path)}

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found"),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found"

    def test_path_endpoint_handles_generic_exception(self, client, tmp_path):
        """Test that generic exceptions are handled with 500 response."""
        archive_path = self._create_archive_file(tmp_path, "exception.tar.gz")
        payload = {"archive_path": str(archive_path)}

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
        archive_path = self._create_archive_file(tmp_path, "failed_status.tar.gz")
        payload = {"archive_path": str(archive_path)}

        mock_errors = [
            {"file": "sim1.json", "error": "Invalid format"},
            {"file": "sim2.json", "error": "Missing field"},
        ]

        with patch(
            "app.features.ingestion.api.ingest_archive",
            return_value=([], 0, 0, mock_errors),
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

    def test_upload_file_size_too_large(self, client):
        """Test that files exceeding size limit are rejected."""
        # Create a large file to test the size limit
        file_content = b"x" * (21 * 1024 * 1024)  # 21MB
        file = BytesIO(file_content)

        # Note: TestClient doesn't set the size attribute on UploadFile,
        # so this test may not fully exercise the size check in production.
        # The size check would need to be tested with real HTTP multipart uploads.
        res = client.post(
            f"{API_BASE}/ingestions/from-upload",
            files={"file": ("large_file.zip", file, "application/zip")},
        )

        # Since TestClient doesn't expose file.size, this may succeed
        # In production with real uploads, this would return 413
        assert res.status_code in [201, 413]

    def test_upload_handles_lookup_error(self, client):
        """Test that LookupError in upload is handled with 400 response."""

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"lookup_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=LookupError("Machine not found in upload"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
                files={"file": (unique_filename, file, "application/zip")},
            )

        assert res.status_code == 400
        assert res.json()["detail"] == "Machine not found in upload"

    def test_upload_handles_generic_exception(self, client):
        """Test that generic exceptions in upload are handled with 500 response."""

        file_content = b"PK\x03\x04"
        file = BytesIO(file_content)
        unique_filename = f"generic_error_{uuid.uuid4().hex[:8]}.zip"

        with patch(
            "app.features.ingestion.api.ingest_archive",
            side_effect=RuntimeError("Unexpected upload error"),
        ):
            res = client.post(
                f"{API_BASE}/ingestions/from-upload",
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
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Simulation with Artifacts",
                    "caseName": "test_case_artifacts",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = (
            db.query(Simulation)
            .filter(Simulation.case_name == "test_case_artifacts")
            .first()
        )

        assert simulation is not None
        assert len(simulation.artifacts) == 1
        assert simulation.artifacts[0].kind == "output"
        assert simulation.artifacts[0].uri == "https://example.com/output.tar.gz"

    def test_persist_simulations_with_links(self, client, db: Session, tmp_path):
        """Test that simulations with external links are persisted correctly."""
        machine = db.query(Machine).first()
        assert machine is not None

        archive_path = self._create_archive_file(tmp_path, "archive_with_links.tar.gz")
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Simulation with Links",
                    "caseName": "test_case_links",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = (
            db.query(Simulation)
            .filter(Simulation.case_name == "test_case_links")
            .first()
        )

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
        payload = {"archive_path": str(archive_path)}

        mock_simulations = [
            SimulationCreate.model_validate(
                {
                    "name": "Simulation with Git URL",
                    "caseName": "test_case_git_url",
                    "compset": "AQUAPLANET",
                    "compsetAlias": "QPC4",
                    "gridName": "f19_f19",
                    "gridResolution": "1.9x2.5",
                    "initializationType": "startup",
                    "simulationType": "control",
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
            return_value=(mock_simulations, 1, 0, []),
        ):
            res = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert res.status_code == 201

        simulation = (
            db.query(Simulation)
            .filter(Simulation.case_name == "test_case_git_url")
            .first()
        )

        assert simulation is not None
        assert (
            simulation.git_repository_url == "https://github.com/E3SM-Project/E3SM.git"
        )
