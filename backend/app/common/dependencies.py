"""
FastAPI dependency functions used across multiple features.

This module provides reusable dependency utilities for the application,
such as database session management. These functions integrate with
FastAPI's dependency injection system and are typically imported in
route handlers using `Depends(...)`.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Provide a SQLAlchemy Session to route handlers.

    This function is used with FastAPI's dependency injection system
    to provide a database session to path operations. It ensures that the
    session is properly closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
