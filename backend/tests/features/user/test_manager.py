from unittest.mock import AsyncMock, patch

import pytest

from app.features.user.manager import UserManager
from app.features.user.models import User


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
