import os
from typing import AsyncGenerator
from urllib.parse import urlparse

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from psycopg.rows import tuple_row
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app._logger import _setup_custom_logger
from app.core.config import settings
from app.db.utils import _make_sync_url
from app.main import app

logger = _setup_custom_logger(__name__)

TEST_DB_URL = settings.test_database_url
ALEMBIC_INI_PATH = "alembic.ini"

# Set up the SQLAlchemy async engine and sessionmaker for testing
async_engine = create_async_engine(TEST_DB_URL, future=True, echo=False)

# NOTE: Keep an async Sessionmaker here, but bind it per-test to a single connection
# that's inside a transaction to ensure isolation.
TestingSessionLocal = async_sessionmaker(
    bind=async_engine, expire_on_commit=False, autoflush=False, autocommit=False
)


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provides a SQLAlchemy AsyncSession for testing, wrapped in a transaction.

    Returns
    -------
    AsyncGenerator[AsyncSession, None]
        An async generator yielding a SQLAlchemy AsyncSession. The session is
        wrapped in a transaction that is rolled back after the test, ensuring
        isolation between tests.
    """
    engine = create_async_engine(settings.test_database_url, echo=False, future=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_client():
    """Provides an AsyncClient for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Sets up a test database for the application (async-aware).

    Steps:
    1. Sets the `DATABASE_URL` environment variable to the test database URL.
    2. Creates the test database.
    3. Runs Alembic migrations to ensure schema consistency.
    4. Drops the database when the test session ends.

    Yields
    ------
    None
        This fixture runs automatically for the session lifecycle.
    """
    os.environ["DATABASE_URL"] = TEST_DB_URL

    _drop_test_database()
    _create_test_database()
    _run_migrations()

    try:
        yield
    finally:
        _drop_test_database()


def _drop_test_database():
    """Drops the test database after the test session ends (PostgreSQL)."""
    logger.info("[pytest teardown] Tearing down test database...")

    TEST_DB_URL = os.environ["DATABASE_URL"]
    db_name, user, password, host, port = _parse_db_url(TEST_DB_URL)

    with psycopg.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port,
        autocommit=True,
    ) as admin_conn:
        with admin_conn.cursor(row_factory=tuple_row) as cur:
            cur.execute("SHOW server_version_num;")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Could not determine PostgreSQL server version")

            (server_version_num,) = row
            server_version_num = int(server_version_num)

            if server_version_num >= 150000:
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE);')
                logger.info(
                    f"[pytest teardown] Dropped test database (FORCE): {db_name}"
                )
            else:
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid();
                    """,
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}";')
                logger.info(f"[pytest teardown] Dropped test database: {db_name}")


def _create_test_database():
    """Creates the PostgreSQL test database if it does not already exist."""
    db_name, user, password, host, port = _parse_db_url(TEST_DB_URL)

    with psycopg.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"[pytest setup] Created test database: {db_name}")
            else:
                logger.info(f"[pytest setup] Using existing test database: {db_name}")


def _parse_db_url(db_url: str) -> tuple[str, str | None, str | None, str, int]:
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip("/")
    user = parsed.username
    password = parsed.password
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    return db_name, user, password, host, port


def _run_migrations():
    """Runs Alembic migrations on the test database."""
    alembic_cfg = Config(ALEMBIC_INI_PATH)
    sync_url = _make_sync_url(TEST_DB_URL)

    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")
