from collections.abc import Generator
from contextlib import contextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides an async SQLAlchemy session.
    """
    async with AsyncSessionLocal() as session:
        yield session


@contextmanager
def transaction(db: Session):
    try:
        yield

        db.commit()
    except IntegrityError as e:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Constraint violation while writing to the database.",
        ) from e
    except Exception:
        db.rollback()

        raise
