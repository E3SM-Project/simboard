"""Integration tests for ingestion with API token authentication."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import status

from app.api.version import API_BASE
from app.features.user.models import ApiToken, User, UserRole
from app.features.user.token_auth import generate_token


def _create_service_account(db):
    """Helper to create a SERVICE_ACCOUNT user for integration tests."""
    user = User(
        email="hpc-bot@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.SERVICE_ACCOUNT,
    )
    db.add(user)
    db.flush()
    db.commit()
    db.refresh(user)
    return user


class TestIngestionWithAPIToken:
    """Integration tests for ingestion using API token authentication."""

    def test_ingest_from_path_with_api_token(self, client, db):
        """Test ingestion from path using API token authentication."""
        # Create SERVICE_ACCOUNT user and API token
        svc_user = _create_service_account(db)
        raw_token, token_hash = generate_token()
        api_token = ApiToken(
            name="HPC Ingestion Token",
            token_hash=token_hash,
            user_id=svc_user.id,
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        # Mock the necessary functions to avoid filesystem/parsing dependencies
        with (
            patch("app.features.ingestion.api._validate_archive_path") as mock_validate,
            patch("app.features.ingestion.api._compute_archive_sha256") as mock_compute,
            patch("app.features.ingestion.api._run_ingest_archive") as mock_ingest,
        ):
            mock_validate.return_value = None
            mock_compute.return_value = "a" * 64

            # Mock ingest result
            mock_result = MagicMock()
            mock_result.created_count = 1
            mock_result.duplicate_count = 0
            mock_result.errors = []
            mock_result.simulations = []
            mock_ingest.return_value = mock_result

            # Create a machine for the test
            from app.features.machine.models import Machine

            machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
            db.add(machine)
            db.commit()

            payload = {
                "archive_path": "/fake/path/archive.tar.gz",
                "machine_name": "test-hpc",
                "hpc_username": "hpc_user123",
            }

            # Make request with Bearer token
            response = client.post(
                f"{API_BASE}/ingestions/from-path",
                json=payload,
                headers={"Authorization": f"Bearer {raw_token}"},
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["created_count"] == 1

    def test_ingest_from_path_with_invalid_token(self, client, db):
        """Test that ingestion with invalid token returns 401."""
        # Create a machine for the test
        from app.features.machine.models import Machine

        machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
        db.add(machine)
        db.commit()

        payload = {
            "archive_path": "/fake/path/archive.tar.gz",
            "machine_name": "test-hpc",
        }

        # Make request with invalid token
        response = client.post(
            f"{API_BASE}/ingestions/from-path",
            json=payload,
            headers={"Authorization": "Bearer invalid_token_12345"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_ingest_from_path_with_revoked_token(self, client, db):
        """Test that ingestion with revoked token returns 401."""
        # Create SERVICE_ACCOUNT user and revoked API token
        svc_user = _create_service_account(db)
        raw_token, token_hash = generate_token()
        api_token = ApiToken(
            name="Revoked Token",
            token_hash=token_hash,
            user_id=svc_user.id,
            created_at=datetime.now(timezone.utc),
            revoked=True,
        )
        db.add(api_token)
        db.commit()

        # Create a machine for the test
        from app.features.machine.models import Machine

        machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
        db.add(machine)
        db.commit()

        payload = {
            "archive_path": "/fake/path/archive.tar.gz",
            "machine_name": "test-hpc",
        }

        # Make request with revoked token
        response = client.post(
            f"{API_BASE}/ingestions/from-path",
            json=payload,
            headers={"Authorization": f"Bearer {raw_token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_ingest_without_authentication(self, client, db):
        """Test that ingestion without authentication returns 401."""
        # Create a machine for the test
        from app.features.machine.models import Machine

        machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
        db.add(machine)
        db.commit()

        payload = {
            "archive_path": "/fake/path/archive.tar.gz",
            "machine_name": "test-hpc",
        }

        # Make request without authentication
        response = client.post(f"{API_BASE}/ingestions/from-path", json=payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_ingest_with_non_service_account_token_rejected(
        self, client, admin_user_sync, db
    ):
        """Test that tokens for non-SERVICE_ACCOUNT users are rejected."""
        raw_token, token_hash = generate_token()
        api_token = ApiToken(
            name="Admin Token",
            token_hash=token_hash,
            user_id=admin_user_sync["id"],
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        from app.features.machine.models import Machine

        machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
        db.add(machine)
        db.commit()

        payload = {
            "archive_path": "/fake/path/archive.tar.gz",
            "machine_name": "test-hpc",
        }

        response = client.post(
            f"{API_BASE}/ingestions/from-path",
            json=payload,
            headers={"Authorization": f"Bearer {raw_token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_hpc_username_stored_with_simulation(self, client, db):
        """Test that hpc_username is stored with simulation when provided."""
        # Create SERVICE_ACCOUNT user and API token
        svc_user = _create_service_account(db)
        raw_token, token_hash = generate_token()
        api_token = ApiToken(
            name="HPC Ingestion Token",
            token_hash=token_hash,
            user_id=svc_user.id,
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        # Create a machine for the test
        from app.features.machine.models import Machine

        machine = Machine(name="test-hpc", hostname="test-hpc.example.com")
        db.add(machine)
        db.commit()

        # Mock the necessary functions
        with (
            patch("app.features.ingestion.api._validate_archive_path") as mock_validate,
            patch("app.features.ingestion.api._compute_archive_sha256") as mock_compute,
            patch("app.features.ingestion.api._run_ingest_archive") as mock_ingest,
        ):
            mock_validate.return_value = None
            mock_compute.return_value = "a" * 64

            # Create a minimal mock simulation
            from app.features.simulation.enums import SimulationStatus, SimulationType
            from app.features.simulation.schemas import SimulationCreate

            mock_sim = SimulationCreate(
                name="test_sim",
                case_name="test_case",
                compset="test_compset",
                compset_alias="test_alias",
                grid_name="test_grid",
                grid_resolution="1x1",
                simulation_type=SimulationType.PRODUCTION,
                status=SimulationStatus.RUNNING,
                initialization_type="cold",
                machine_id=machine.id,
                simulation_start_date=datetime.now(timezone.utc),
            )

            mock_result = MagicMock()
            mock_result.created_count = 1
            mock_result.duplicate_count = 0
            mock_result.errors = []
            mock_result.simulations = [mock_sim]
            mock_ingest.return_value = mock_result

            payload = {
                "archive_path": "/fake/path/archive.tar.gz",
                "machine_name": "test-hpc",
                "hpc_username": "hpc_user_test",
            }

            response = client.post(
                f"{API_BASE}/ingestions/from-path",
                json=payload,
                headers={"Authorization": f"Bearer {raw_token}"},
            )

            assert response.status_code == status.HTTP_201_CREATED

            # Verify hpc_username was stored
            from app.features.simulation.models import Simulation

            simulation = (
                db.query(Simulation).filter(Simulation.name == "test_sim").first()
            )
            assert simulation is not None
            assert simulation.hpc_username == "hpc_user_test"
