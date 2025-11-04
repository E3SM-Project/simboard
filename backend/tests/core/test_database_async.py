import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_async import _make_async_url, get_async_session


class TestMakeAsyncUrl:
    @pytest.mark.parametrize(
        "sync_url, expected_async_url",
        [
            (
                "postgresql+psycopg://user:password@localhost/dbname",
                "postgresql+asyncpg://user:password@localhost/dbname",
            ),
            (
                "postgresql+psycopg://user:password@127.0.0.1/dbname",
                "postgresql+asyncpg://user:password@127.0.0.1/dbname",
            ),
        ],
    )
    def test_valid(self, sync_url, expected_async_url):
        """Test that _make_async_url correctly converts valid sync URLs to async URLs."""
        assert _make_async_url(sync_url) == expected_async_url

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "mysql://user:password@localhost/dbname",
            "sqlite:///test.db",
            "postgresql://user:password@localhost/dbname",
        ],
    )
    def test_invalid(self, invalid_url):
        """Test that _make_async_url raises ValueError for unsupported URL schemes."""
        with pytest.raises(
            ValueError, match="Unsupported database URL scheme for async conversion."
        ):
            _make_async_url(invalid_url)


class TestGetAsyncSession:
    @pytest.mark.asyncio
    async def test_session_instance(self):
        """Test that get_async_session yields a valid AsyncSession instance."""
        async_gen = get_async_session()
        session = await async_gen.asend(None)

        try:
            assert isinstance(session, AsyncSession)
            result = await session.execute(text("SELECT 1"))

            assert result.scalar() == 1
        finally:
            await async_gen.aclose()
