"""Main application setup for the FastAPI backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app._logger import _setup_root_logger
from app.api.routers import ai, machine, simulation
from app.auth.user import auth_backend, fastapi_users
from app.core.config import settings
from app.exceptions import register_exception_handlers
from app.schemas.user import UserCreate, UserRead, UserUpdate


def create_app() -> FastAPI:
    _setup_root_logger()

    app = FastAPI(title="EarthFrame API")

    # Register custom exception handlers that map SQLAlchemy errors to HTTP
    # responses.
    register_exception_handlers(app)

    # CORS setup
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers.
    app.include_router(ai.router)
    app.include_router(simulation.router)
    app.include_router(machine.router)

    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )

    return app


# This instance is used by uvicorn: `uvicorn app.main:app`
app = create_app()
