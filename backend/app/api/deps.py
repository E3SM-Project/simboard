from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides an async SQLAlchemy session.
    """
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def transaction(session: AsyncSession):
    """
    Context manager to run a block of code within a transaction.

    Rolls back on error and raises an HTTPException if a constraint is violated.
    """
    try:
        yield
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Constraint violation while writing to the database.",
        ) from e
    except Exception:
        await session.rollback()
        raise
