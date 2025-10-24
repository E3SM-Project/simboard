from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session, transaction


class TestGetAsyncSession:
    async def test_get_async_session(self):
        mock_session = AsyncMock(spec=AsyncSession)

        # Patch AsyncSessionLocal to return an async context manager
        async_cm = AsyncMock()
        async_cm.__aenter__.return_value = mock_session
        async_cm.__aexit__.return_value = None

        with patch("app.api.deps.AsyncSessionLocal", return_value=async_cm):
            async_generator = get_async_session()
            db = await async_generator.__anext__()

            assert db == mock_session
            async_cm.__aenter__.assert_called_once()
            async_cm.__aexit__.assert_not_called()

            with pytest.raises(StopAsyncIteration):
                await async_generator.__anext__()

            async_cm.__aexit__.assert_called_once()


class TestTransaction:
    async def test_transaction_commit(self):
        mock_session = AsyncMock(spec=AsyncSession)

        async with transaction(mock_session):
            mock_session.commit.assert_not_called()

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_called()

    async def test_transaction_integrity_error(self):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit.side_effect = IntegrityError(
            "mock", "mock", Exception("mock")
        )

        with pytest.raises(HTTPException) as exc_info:
            async with transaction(mock_session):
                pass

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert (
            exc_info.value.detail
            == "Constraint violation while writing to the database."
        )
        mock_session.rollback.assert_awaited_once()

    async def test_transaction_generic_exception(self):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit.side_effect = Exception("Generic error")

        with pytest.raises(Exception, match="Generic error"):
            async with transaction(mock_session):
                pass

        mock_session.rollback.assert_awaited_once()
