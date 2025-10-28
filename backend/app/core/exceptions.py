"""
This module provides custom exception handling for a FastAPI application.

It includes mappings for SQLAlchemy exceptions to HTTP status codes and error
messages, as well as handlers for SQLAlchemy errors, FlushError, and Pydantic
ValidationError. These handlers ensure consistent and user-friendly error
responses for the application.
"""

import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm.exc import FlushError

from app.core.logger import _setup_custom_logger

logger = _setup_custom_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for the FastAPI application.

    This function sets up custom exception handlers for SQLAlchemy errors,
    FlushError, and Pydantic ValidationError to provide consistent and
    user-friendly error responses.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance to register the exception handlers with.

    Returns
    -------
    None
    """

    @app.exception_handler(sa_exc.SQLAlchemyError)
    async def handle_sqlalchemy_error(
        _: FastAPI, e: sa_exc.SQLAlchemyError
    ) -> JSONResponse:
        """Handle SQLAlchemy errors and return appropriate JSON responses.

        Parameters
        ----------
        _ : FastAPI
            The FastAPI application instance (unused).
        e : sa_exc.SQLAlchemyError
            The SQLAlchemy error instance.

        Returns
        -------
        JSONResponse
            The JSON response with the appropriate status code and error detail.
        """
        status_code, detail = map_sa_exception(e)

        return JSONResponse(status_code=status_code, content={"detail": detail})

    @app.exception_handler(FlushError)
    async def handle_flush_error(_: FastAPI, e: FlushError) -> JSONResponse:
        """Handle FlushError and return appropriate JSON responses.

        Parameters
        ----------
        _ : FastAPI
            The FastAPI application instance (unused).
        e : FlushError
            The FlushError instance.

        Returns
        -------
        JSONResponse
            The JSON response with the appropriate status code and error detail.
        """
        status_code, detail = map_sa_exception(e)

        return JSONResponse(status_code=status_code, content={"detail": detail})

    @app.exception_handler(ValidationError)
    async def handle_response_validation(
        _: FastAPI, e: ValidationError
    ) -> JSONResponse:
        """
        Handle Pydantic ValidationError and return appropriate JSON responses.

        Parameters
        ----------
        _ : FastAPI
            The FastAPI application instance (unused).
        e : ValidationError
            The Pydantic ValidationError instance.

        Returns
        -------
        JSONResponse
            The JSON response with a 500 status code and error detail.
        """
        logger.error("Response model validation failed", exc_info=True)

        return JSONResponse(
            status_code=500, content={"detail": "Internal serialization error."}
        )


def map_sa_exception(e: Exception) -> tuple[int, str]:
    """Map a SQLAlchemy exception to an HTTP status code and error message.

    This function takes a SQLAlchemy exception and returns a tuple containing
    an appropriate HTTP status code and a user-friendly error message.

    Parameters
    ----------
    e : Exception
        The SQLAlchemy exception instance to map.

    Returns
    -------
    tuple[int, str]
        A tuple containing the HTTP status code and the error message.
    """
    logger.error("\n--- SQLAlchemy Exception Traceback ---\n%s", traceback.format_exc())
    logger.error(
        "\n--- Exception Details ---\n"
        "Type: %s\n"
        "Message: %s\n"
        "--------------------------",
        type(e).__name__,
        str(e),
    )

    if isinstance(e, sa_exc.IntegrityError):
        return pg_detail(e)
    elif isinstance(e, sa_exc.DataError):
        return 400, "Invalid data for a column."
    elif isinstance(e, (sa_exc.InvalidRequestError, FlushError)):
        return 400, "Invalid ORM operation or state."
    elif isinstance(e, sa_exc.OperationalError):
        return 503, "Database unavailable; try again."
    elif isinstance(e, sa_exc.DBAPIError):
        code = 503 if getattr(e, "connection_invalidated", False) else 500
        return code, "Database error."

    return 500, "Unexpected server error."


def pg_detail(e: sa_exc.IntegrityError) -> tuple[int, str]:
    """Extract PostgreSQL-specific details from an IntegrityError.

    This function inspects the PostgreSQL error code (pgcode) from the
    IntegrityError and returns an appropriate HTTP status code and error message.

    Parameters
    ----------
    e : sa_exc.IntegrityError
        The IntegrityError instance to extract details from.

    Returns
    -------
    tuple[int, str]
        A tuple containing the HTTP status code and the error message.
    """
    pgcode: str | None = getattr(getattr(e, "orig", None), "pgcode", None)

    # Log the error details
    logger.error(f"IntegrityError occurred: {e}")

    if pgcode == "23505":  # unique_violation (Postgres)
        return 409, "Duplicate resource (unique constraint)."
    elif pgcode == "23503":  # foreign_key_violation
        return 400, "Invalid reference (foreign key)."
    elif pgcode == "23502":  # not_null_violation
        return 400, "Missing required value (not-null constraint)."

    return 409, "Constraint violation."
