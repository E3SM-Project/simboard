"""Integration tests for API token management endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi import status

from app.api.version import API_BASE
from app.features.user.models import ApiToken, User
from app.features.user.token_auth import generate_token


@pytest.mark.skip(reason="Async tests not yet running properly")
class TestTokenManagementAPI:
    """Integration tests for token management endpoints."""

    async def test_create_token_as_admin(
        self, client, admin_user_sync, normal_user_sync, db
    ):
        """Test that an admin can create an API token."""

        # Mock admin authentication
        def override_current_active_user():
            return db.query(User).filter(User.id == admin_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            payload = {
                "name": "Test Token",
                "user_id": str(normal_user_sync["id"]),
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

    async def test_create_token_as_non_admin(self, client, normal_user_sync, db):
        """Test that a non-admin cannot create an API token."""

        def override_current_active_user():
            return db.query(User).filter(User.id == normal_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            payload = {
                "name": "Test Token",
                "user_id": str(normal_user_sync["id"]),
            }

            response = client.post(f"{API_BASE}/tokens", json=payload)

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    async def test_list_tokens_as_admin(
        self, client, admin_user_sync, normal_user_sync, db
    ):
        """Test that an admin can list all API tokens."""
        # Create a token first
        raw_token, token_hash = generate_token()
        api_token = ApiToken(
            name="Test Token",
            token_hash=token_hash,
            user_id=normal_user_sync["id"],
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        def override_current_active_user():
            return db.query(User).filter(User.id == admin_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            response = client.get(f"{API_BASE}/tokens")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert any(token["name"] == "Test Token" for token in data)
        finally:
            app.dependency_overrides.clear()

    async def test_list_tokens_as_non_admin(self, client, normal_user_sync, db):
        """Test that a non-admin cannot list API tokens."""

        def override_current_active_user():
            return db.query(User).filter(User.id == normal_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            response = client.get(f"{API_BASE}/tokens")

            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    async def test_revoke_token_as_admin(
        self, client, admin_user_sync, normal_user_sync, db
    ):
        """Test that an admin can revoke an API token."""
        # Create a token first
        raw_token, token_hash = generate_token()
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

        def override_current_active_user():
            return db.query(User).filter(User.id == admin_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            response = client.delete(f"{API_BASE}/tokens/{token_id}")

            assert response.status_code == status.HTTP_204_NO_CONTENT

            # Verify token is revoked
            db.expire_all()
            revoked_token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
            assert revoked_token.revoked is True
        finally:
            app.dependency_overrides.clear()

    async def test_revoke_token_not_found(self, client, admin_user_sync, db):
        """Test that revoking a non-existent token returns 404."""

        def override_current_active_user():
            return db.query(User).filter(User.id == admin_user_sync["id"]).first()

        from app.features.user.manager import current_active_user
        from app.main import app

        app.dependency_overrides[current_active_user] = override_current_active_user

        try:
            fake_id = "00000000-0000-0000-0000-000000000000"
            response = client.delete(f"{API_BASE}/tokens/{fake_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()
