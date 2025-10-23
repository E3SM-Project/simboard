from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from app.db.models.base import Base
from sqlalchemy import engine_from_config, pool

from app import db  # noqa: F401  # import all SQLALchemy models so Alembic sees them
from app._logger import _setup_custom_logger
from app.core.config import settings
from app.db.utils import _make_sync_url

logger = _setup_custom_logger(__name__)

# --- Ensure project is importable (backend root = parent of 'app') ---
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


# This is the Alembic Config object, which provides access to the values within
# the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Only set URL if it hasn't already been overridden (e.g., by test code)
# NOTE: Alembic expects a sync URL, so we convert it here.
if not config.get_main_option("sqlalchemy.url"):
    sync_url = _make_sync_url(settings.database_url)
    config.set_main_option("sqlalchemy.url", sync_url)


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
    """Run migrations in 'online' mode'"""
    # Don't override sqlalchemy.url here — it may already be set externally
    # (e.g., by tests)
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
            logger.info("[env.py] 🚀 Running migrations for:", url)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
