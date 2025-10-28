from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _make_async_url(url: str) -> str:
    """Convert a synchronous database URL to its asynchronous counterpart."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    else:
        raise ValueError("Unsupported database URL scheme for async conversion.")


engine = create_async_engine(
    _make_async_url(settings.database_url),
    pool_pre_ping=True,
    echo=False,  # optional: set True for SQL logging during development
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
