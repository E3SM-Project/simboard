from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.health import router as health_router
from app.api.meta import router as meta_router
from app.api.metadata_backfill import router as metadata_backfill_router
from app.api.source_directories import router as source_directories_router
from app.api.version import API_BASE
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import _setup_root_logger
from app.features.assistant.api import (
    execution_router as execution_assistant_router,
)
from app.features.catalog.api import case_router, diagnostics_router, execution_router
from app.features.diagnostics.api import router as diagnostics_compare_router
from app.features.ingestion.api import router as ingestion_router
from app.features.machine.api import router as machine_router
from app.features.pace.api import router as pace_router
from app.features.site.api import router as site_router
from app.features.user.api.oauth import auth_router, user_router
from app.features.user.api.token import router as token_router


def create_app() -> FastAPI:
    _setup_root_logger()

    app = FastAPI(title="SimBoard API")

    # Register custom exception handlers that map SQLAlchemy errors to HTTP
    # responses.
    register_exception_handlers(app)

    # CORS setup
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Diagnostics comparisons run to hundreds of kilobytes of repetitive JSON.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Register routers.
    app.include_router(execution_router, prefix=API_BASE)
    app.include_router(diagnostics_router, prefix=API_BASE)
    app.include_router(diagnostics_compare_router, prefix=API_BASE)
    app.include_router(execution_assistant_router, prefix=API_BASE)
    app.include_router(case_router, prefix=API_BASE)
    app.include_router(machine_router, prefix=API_BASE)
    app.include_router(site_router, prefix=API_BASE)
    app.include_router(pace_router, prefix=API_BASE)
    app.include_router(user_router, prefix=API_BASE)
    app.include_router(auth_router, prefix=API_BASE)
    app.include_router(token_router, prefix=API_BASE)
    app.include_router(ingestion_router, prefix=API_BASE)
    app.include_router(source_directories_router, prefix=API_BASE)
    app.include_router(metadata_backfill_router, prefix=API_BASE)
    app.include_router(meta_router, prefix=API_BASE)
    app.include_router(health_router, prefix=API_BASE)

    return app


# This instance is used by uvicorn: `uvicorn app.main:app`
app = create_app()
