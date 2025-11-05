from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# import all SQLAlchemy models so Alembic sees them
import app.models  # noqa: F401
from app.common.models.base import Base
from app.core.config import settings
from app.core.logger import _setup_custom_logger

# --- Ensure project is importable (backend root = parent of 'app') ---
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


logger = _setup_custom_logger(__name__)

# --- Alembic Config Setup ---
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Database URL ---
if not config.get_main_option("sqlalchemy.url"):
    db_url = settings.database_url
    config.set_main_option("sqlalchemy.url", db_url)
    logger.debug(f"[env.py] Using database URL from settings: {db_url}")

# --- Target Metadata ---
target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    url = config.get_main_option("sqlalchemy.url")

    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            logger.info(f"[env.py] 🚀 Running migrations for: {url}")
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
