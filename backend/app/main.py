from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import _setup_root_logger
from app.features.machine.api import router as machine_router
from app.features.simulation.api import router as simulations_router
from app.features.user.api import auth_router, user_router


def create_app() -> FastAPI:
    _setup_root_logger()

    app = FastAPI(title="SimBoard API")

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
    app.include_router(simulations_router, prefix="/api")
    app.include_router(machine_router, prefix="/api")
    app.include_router(user_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# This instance is used by uvicorn: `uvicorn app.main:app`
app = create_app()
