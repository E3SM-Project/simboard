"""
FastAPI dependency functions used across multiple features.

This module provides reusable dependency utilities for the application,
such as database session management. These functions integrate with
FastAPI's dependency injection system and are typically imported in
route handlers using `Depends(...)`.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_database_session() -> Generator[Session, None, None]:
    """Provide a SQLAlchemy database session to route handlers.

    This function is used with FastAPI's dependency injection system
    to provide a database session to path operations. It ensures that the
    session is properly closed after use.
    """
    db_session = SessionLocal()

    try:
        yield db_session
    finally:
        db_session.close()
