from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import _setup_root_logger
from app.features.machine.api import router as machine_router
from app.features.simulation.api import router as simulations_router
from app.features.user.manager import fastapi_users
from app.features.user.schemas import UserCreate, UserRead, UserUpdate


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
    app.include_router(simulations_router)
    app.include_router(machine_router)
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
