from contextlib import contextmanager

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# SQLAlchemy 2.0-style engine (sync)
engine = create_engine(settings.database_url, pool_pre_ping=True)


# autoflush=False: Disables auto flushing of changes before a query for control.
# autocommit=False: Requires explicit commit for better transaction control.
# future=True: Enables SQLAlchemy 2.0-style behavior for forward compatibility.
# expire_on_commit=False: Prevents auto-expiry of objects post commit for performance.
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False
)


@contextmanager
def transaction(db: Session):
    """Context manager for handling database transactions.

    This function provides a transactional scope around a series of operations.

    Parameters:
    -----------
    db : Session
        An active SQLAlchemy Session object.

    Yields:
    -------
    Session
        The provided SQLAlchemy Session object within a transaction.
    """
    try:
        yield db

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
