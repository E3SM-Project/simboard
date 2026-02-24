import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.features.user.manager import UserManager, current_active_user
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
