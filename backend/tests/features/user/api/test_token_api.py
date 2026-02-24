"""Integration tests for API token management endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi import status

from app.api.version import API_BASE
from app.common.models.base import Base
from app.core.config import settings
from app.features.user.auth.token_auth import generate_token
from app.features.user.manager import current_active_user
from app.features.user.models import ApiToken, User, UserRole
from app.main import app
from tests.conftest import engine


@pytest.fixture(autouse=True, scope="module")
def _ensure_tables():
    """Recreate tables if they were dropped by async_db fixtures.

    The async_db fixture (conftest.py) calls Base.metadata.drop_all after
    each async test.  create_all is idempotent — it only creates tables
    that are missing.
    """
    Base.metadata.create_all(bind=engine)
    yield


def _override_as_user(db, user_info):
    """Override current_active_user to return the given user."""
    user = db.query(User).filter(User.id == user_info["id"]).first()
    app.dependency_overrides[current_active_user] = lambda: user


def _create_service_account_user(db, email: str = "token-bot@example.com") -> User:
    """Create a SERVICE_ACCOUNT user for token creation tests."""
    user = User(
        email=email,
        is_active=True,
        is_verified=True,
        role=UserRole.SERVICE_ACCOUNT,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestTokenManagementAPI:
    """Integration tests for token management endpoints."""

    def test_raises_if_user_id_does_not_exist(self, client, admin_user_sync, db):
        """Test that creating a token with a non-existent user_id raises 404."""
        _override_as_user(db, admin_user_sync)

        try:
            payload = {
                "name": "Test Token",
                "user_id": "00000000-0000-0000-0000-000000000000",
            }

            response = client.post(f"{API_BASE}/tokens", json=payload)

            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_create_token_as_admin(self, client, admin_user_sync, db):
        """Test that an admin can create an API token for a service account."""
        _override_as_user(db, admin_user_sync)
        service_user = _create_service_account_user(db, "token-create-bot@example.com")

        try:
            payload = {
                "name": "Test Token",
                "user_id": str(service_user.id),
            }

            response = client.post(f"{API_BASE}/tokens", json=payload)

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert "token" in data
            assert data["token"].startswith("sbk_")
            assert data["name"] == "Test Token"
            assert "id" in data
        finally:
            app.dependency_overrides.clear()

    def test_create_token_rejects_non_service_account_user(
        self, client, admin_user_sync, normal_user_sync, db
    ):
        """Test that creating a token for a non-SERVICE_ACCOUNT user fails."""
        _override_as_user(db, admin_user_sync)

        try:
            payload = {
                "name": "Test Token",
                "user_id": str(normal_user_sync["id"]),
            }

            response = client.post(f"{API_BASE}/tokens", json=payload)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert (
                response.json()["detail"]
                == "API tokens can only be created for SERVICE_ACCOUNT users"
            )
        finally:
            app.dependency_overrides.clear()

    def test_create_token_as_non_admin(self, client, normal_user_sync, db):
        """Test that a non-admin cannot create an API token."""
        _override_as_user(db, normal_user_sync)

        try:
            payload = {
                "name": "Test Token",
                "user_id": str(normal_user_sync["id"]),
            }

            response = client.post(f"{API_BASE}/tokens", json=payload)

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    def test_list_tokens_as_admin(self, client, admin_user_sync, normal_user_sync, db):
        """Test that an admin can list all API tokens."""
        _, token_hash = generate_token()
        api_token = ApiToken(
            name="Test Token",
            token_hash=token_hash,
            user_id=normal_user_sync["id"],
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        _override_as_user(db, admin_user_sync)

        try:
            response = client.get(f"{API_BASE}/tokens")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert any(token["name"] == "Test Token" for token in data)
        finally:
            app.dependency_overrides.clear()

    def test_list_tokens_as_non_admin(self, client, normal_user_sync, db):
        """Test that a non-admin cannot list API tokens."""
        _override_as_user(db, normal_user_sync)

        try:
            response = client.get(f"{API_BASE}/tokens")

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    def test_revoke_token_as_admin(self, client, admin_user_sync, normal_user_sync, db):
        """Test that an admin can revoke an API token."""
        _, token_hash = generate_token()
        api_token = ApiToken(
            name="Token to Revoke",
            token_hash=token_hash,
            user_id=normal_user_sync["id"],
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()
        db.refresh(api_token)
        token_id = api_token.id

        _override_as_user(db, admin_user_sync)

        try:
            response = client.delete(f"{API_BASE}/tokens/{token_id}")

            assert response.status_code == status.HTTP_204_NO_CONTENT

            db.expire_all()
            revoked_token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
            assert revoked_token.revoked is True
        finally:
            app.dependency_overrides.clear()

    def test_revoke_token_not_found(self, client, admin_user_sync, db):
        """Test that revoking a non-existent token returns 404."""
        _override_as_user(db, admin_user_sync)

        try:
            fake_id = "00000000-0000-0000-0000-000000000000"
            response = client.delete(f"{API_BASE}/tokens/{fake_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_revoke_token_as_non_admin(
        self, client, normal_user_sync, admin_user_sync, db
    ):
        """Test that a non-admin cannot revoke an API token."""
        _, token_hash = generate_token()
        api_token = ApiToken(
            name="Token to Revoke",
            token_hash=token_hash,
            user_id=admin_user_sync["id"],
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()
        db.refresh(api_token)
        token_id = api_token.id

        _override_as_user(db, normal_user_sync)

        try:
            response = client.delete(f"{API_BASE}/tokens/{token_id}")

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    def test_create_service_account_as_admin(self, client, admin_user_sync, db):
        """Test that an admin can create a service account."""
        _override_as_user(db, admin_user_sync)

        try:
            payload = {"service_name": "test-bot"}

            response = client.post(f"{API_BASE}/tokens/service-accounts", json=payload)

            assert response.status_code in (
                status.HTTP_200_OK,
                status.HTTP_201_CREATED,
            )
            data = response.json()
            assert data["email"] == f"test-bot@{settings.domain}"
            assert data["role"] == UserRole.SERVICE_ACCOUNT.value
            assert data["created"] is True
        finally:
            app.dependency_overrides.clear()

    def test_create_service_account_idempotent(self, client, admin_user_sync, db):
        """Test that creating a duplicate service account returns existing."""
        _override_as_user(db, admin_user_sync)

        try:
            payload = {"service_name": "idempotent-bot"}

            # First call creates
            response1 = client.post(f"{API_BASE}/tokens/service-accounts", json=payload)
            assert response1.status_code in (
                status.HTTP_200_OK,
                status.HTTP_201_CREATED,
            )
            data1 = response1.json()
            assert data1["created"] is True

            # Second call returns existing
            response2 = client.post(f"{API_BASE}/tokens/service-accounts", json=payload)
            assert response2.status_code == status.HTTP_200_OK
            data2 = response2.json()
            assert data2["created"] is False
            assert data2["id"] == data1["id"]
        finally:
            app.dependency_overrides.clear()

    def test_create_service_account_as_non_admin(self, client, normal_user_sync, db):
        """Test that a non-admin cannot create a service account."""
        _override_as_user(db, normal_user_sync)

        try:
            payload = {"service_name": "test-bot"}

            response = client.post(f"{API_BASE}/tokens/service-accounts", json=payload)

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()
