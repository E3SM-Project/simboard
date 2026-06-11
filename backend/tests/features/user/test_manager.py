import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.features.user.manager import (
    UserManager,
    can_edit_managed_content,
    current_active_user,
    optional_current_user,
)
from app.features.user.models import User, UserRole


class TestUserManager:
    @pytest.mark.asyncio
    async def test_on_after_register_logs_message(self):
        # Arrange
        user = User(email="testuser@example.com")
        user_manager = UserManager(user_db=AsyncMock())
        logger_patch = "app.features.user.manager.logger.info"

        # Act
        with patch(logger_patch) as mock_logger:
            await user_manager.on_after_register(user)

        # Assert
        mock_logger.assert_called_once_with(
            "✅ New GitHub user registered: testuser@example.com"
        )

    @pytest.mark.asyncio
    async def test_refresh_membership_persists_verified_state(self):
        checked_at = datetime.now(timezone.utc)
        user = User(
            id=uuid.uuid4(),
            email="testuser@example.com",
            role=UserRole.USER,
        )
        user_db = AsyncMock()
        user_manager = UserManager(user_db=user_db)

        await user_manager.refresh_github_org_membership(
            user,
            is_verified_member=True,
            checked_at=checked_at,
        )

        user_db.update.assert_awaited_once_with(
            user,
            {
                "has_verified_e3sm_membership": True,
                "github_org_membership_checked_at": checked_at,
            },
        )

    @pytest.mark.asyncio
    async def test_refresh_membership_persists_verified_state_for_admin(self):
        checked_at = datetime.now(timezone.utc)
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            role=UserRole.ADMIN,
        )
        user_db = AsyncMock()
        user_manager = UserManager(user_db=user_db)

        await user_manager.refresh_github_org_membership(
            user,
            is_verified_member=True,
            checked_at=checked_at,
        )

        user_db.update.assert_awaited_once_with(
            user,
            {
                "has_verified_e3sm_membership": True,
                "github_org_membership_checked_at": checked_at,
            },
        )

    @pytest.mark.asyncio
    async def test_refresh_membership_persists_unverified_state(self):
        checked_at = datetime.now(timezone.utc)
        user = User(
            id=uuid.uuid4(),
            email="user@example.com",
            role=UserRole.USER,
        )
        user_db = AsyncMock()
        user_manager = UserManager(user_db=user_db)

        await user_manager.refresh_github_org_membership(
            user,
            is_verified_member=False,
            checked_at=checked_at,
        )

        user_db.update.assert_awaited_once_with(
            user,
            {
                "has_verified_e3sm_membership": False,
                "github_org_membership_checked_at": checked_at,
            },
        )


class TestCurrentActiveUser:
    """Tests for the unified current_active_user dependency."""

    @pytest.mark.asyncio
    async def test_returns_oauth_user_when_present(self):
        """OAuth user takes precedence when available."""
        oauth_user = User(
            id=uuid.uuid4(),
            email="oauth@example.com",
            role=UserRole.USER,
        )
        request = MagicMock()
        db = MagicMock()

        result = await current_active_user(
            request=request, oauth_user=oauth_user, db=db
        )

        assert result is oauth_user

    @pytest.mark.asyncio
    async def test_raises_401_when_no_auth_header(self):
        """Raises 401 when no OAuth user and no Authorization header."""
        request = MagicMock()
        request.headers.get.return_value = None
        db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await current_active_user(request=request, oauth_user=None, db=db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"

    @pytest.mark.asyncio
    async def test_raises_401_for_invalid_auth_format(self):
        """Raises 401 when Authorization header has wrong format."""
        request = MagicMock()
        request.headers.get.return_value = "Basic abc123"
        db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await current_active_user(request=request, oauth_user=None, db=db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid authentication credentials"

    @pytest.mark.asyncio
    async def test_raises_401_for_malformed_bearer(self):
        """Raises 401 when Bearer token is malformed (too many parts)."""
        request = MagicMock()
        request.headers.get.return_value = "Bearer token extra"
        db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await current_active_user(request=request, oauth_user=None, db=db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid authentication credentials"

    @pytest.mark.asyncio
    async def test_raises_401_for_invalid_token(self):
        """Raises 401 when token validation fails."""
        request = MagicMock()
        request.headers.get.return_value = "Bearer sbk_invalid"
        db = MagicMock()

        with patch("app.features.user.manager.validate_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await current_active_user(request=request, oauth_user=None, db=db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_returns_user_for_valid_token(self):
        """Returns user when token validation succeeds."""
        request = MagicMock()
        request.headers.get.return_value = "Bearer sbk_valid_token"
        db = MagicMock()

        expected_user = User(
            id=uuid.uuid4(),
            email="svc@example.com",
            role=UserRole.SERVICE_ACCOUNT,
        )

        with patch(
            "app.features.user.manager.validate_token",
            return_value=expected_user,
        ):
            result = await current_active_user(request=request, oauth_user=None, db=db)

        assert result is expected_user


class TestOptionalCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_oauth_user_when_present(self):
        oauth_user = User(
            id=uuid.uuid4(),
            email="oauth@example.com",
            role=UserRole.USER,
        )
        request = MagicMock()
        db = MagicMock()

        result = await optional_current_user(
            request=request, oauth_user=oauth_user, db=db
        )

        assert result is oauth_user

    @pytest.mark.asyncio
    async def test_returns_none_when_no_auth_header(self):
        request = MagicMock()
        request.headers.get.return_value = None
        db = MagicMock()

        result = await optional_current_user(request=request, oauth_user=None, db=db)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_for_valid_token(self):
        request = MagicMock()
        request.headers.get.return_value = "Bearer sbk_valid_token"
        db = MagicMock()

        expected_user = User(
            id=uuid.uuid4(),
            email="svc@example.com",
            role=UserRole.SERVICE_ACCOUNT,
        )

        with patch(
            "app.features.user.manager.validate_token",
            return_value=expected_user,
        ):
            result = await optional_current_user(
                request=request, oauth_user=None, db=db
            )

        assert result is expected_user


class TestCanEditManagedContent:
    def test_none_user_denied(self):
        assert can_edit_managed_content(None) is False

    def test_admin_allowed_without_org_membership(self):
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            role=UserRole.ADMIN,
            has_verified_e3sm_membership=False,
        )

        assert can_edit_managed_content(user) is True

    def test_verified_membership_enables_edit_capability(self):
        user = User(
            id=uuid.uuid4(),
            email="user@example.com",
            role=UserRole.USER,
            has_verified_e3sm_membership=True,
        )

        assert can_edit_managed_content(user) is True
        user.has_verified_e3sm_membership = False
        assert can_edit_managed_content(user) is False

    def test_unverified_user_and_service_account_are_denied(self):
        assert (
            can_edit_managed_content(
                User(
                    id=uuid.uuid4(),
                    email="user@example.com",
                    role=UserRole.USER,
                    has_verified_e3sm_membership=False,
                )
            )
            is False
        )
        assert (
            can_edit_managed_content(
                User(
                    id=uuid.uuid4(),
                    email="svc@example.com",
                    role=UserRole.SERVICE_ACCOUNT,
                    has_verified_e3sm_membership=True,
                )
            )
            is False
        )
