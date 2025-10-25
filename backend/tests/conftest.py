import os
from typing import Generator
from urllib.parse import urlparse

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.rows import tuple_row
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.common.dependencies import get_database_session
from app.core.config import settings
from app.core.logger import _setup_custom_logger
from app.main import app

logger = _setup_custom_logger(__name__)

TEST_DB_URL = settings.test_database_url
ALEMBIC_INI_PATH = "alembic.ini"

# Set up the SQLAlchemy engine and sessionmaker for testing
engine = create_engine(TEST_DB_URL, future=True)

# NOTE: Keep a Sessionmaker here, but bind it per-test to a single connection
# that's inside a transaction to ensure isolation.
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, expire_on_commit=False, future=True
)


@pytest.fixture(scope="session")
def _connection():
    # Keep a single physical connection open for the whole test session (fast).
    # Tests will run inside per-test transactions on this connection.
    with engine.connect() as conn:
        yield conn


@pytest.fixture(scope="function")
def db(_connection) -> Generator[Session, None, None]:
    """
    Provides a new SQLAlchemy session for each test.

    This fixture sets up a fresh database session for every test, ensuring
    isolation and allowing direct access to the test database for assertions.

    Yields
    ------
    Session
        A SQLAlchemy session connected to the test database.

    Notes
    -----
    The session is automatically closed after the test completes.
    """
    # Begin an outer transaction for this test, and start a SAVEPOINT (nested).
    # This ensures that any commits inside the test are contained and rolled back.
    outer_tx = _connection.begin()
    nested_tx = _connection.begin_nested()

    # Bind the Session to the shared connection (inside the transaction).
    session: Session = TestingSessionLocal(bind=_connection)

    # After each nested transaction ends (e.g., after a commit),
    # automatically start a new SAVEPOINT so the Session remains usable.
    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, txn):
        if txn.nested and not txn._parent.nested:
            _connection.begin_nested()

    try:
        yield session
    finally:
        # Roll back everything done in the test and close the session.
        session.close()

        # Safe to call rollback even if already ended.
        nested_tx.rollback()
        outer_tx.rollback()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Sets up a test database for the application.

    This function performs the following steps:
    1. Sets the `DATABASE_URL` environment variable to the test database URL.
    2. Creates the test database.
    3. Runs database migrations to ensure the schema is up-to-date.

    Yields
    ------
    None
        This function is a generator and is intended to be used as a fixture
        or context manager for setting up and tearing down the test database.
    """
    # Make DATABASE_URL available to the app in case it reads from env.
    os.environ["DATABASE_URL"] = TEST_DB_URL

    # Ensure a clean state by dropping any existing test database.
    _drop_test_database()
    _create_test_database()
    _run_migrations()

    try:
        yield
    finally:
        _drop_test_database()


def _drop_test_database():
    """Drops the test database after the test session ends.

    This function ensures that the test database is cleaned up
    and removed once all tests have completed.

    Notes
    -----
    - This function assumes that the `TEST_DB_URL` contains the connection
        string for the test database.
    - The function requires the `psycopg` library for PostgreSQL database interaction.
    """
    logger.info("[pytest teardown] Tearing down test database...")

    TEST_DB_URL = os.environ["DATABASE_URL"]  # or import your constant
    db_name, user, password, host, port = _parse_db_url(TEST_DB_URL)

    # Connect to a maintenance DB to manage/drop the test DB.
    with psycopg.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port,
        autocommit=True,
    ) as admin_conn:
        with admin_conn.cursor(row_factory=tuple_row) as cur:
            # Detect server version
            cur.execute("SHOW server_version_num;")
            result = cur.fetchone()

            if result is None:
                raise ValueError("Failed to fetch server version number.")

            (server_version_num,) = result
            server_version_num = int(server_version_num)

            if server_version_num >= 150000:
                # PostgreSQL 15+ supports FORCE
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE);')
                logger.info(
                    f"[pytest teardown] Dropped test database with FORCE: {db_name}"
                )
            else:
                # Pre-15: terminate connections, then drop
                # 1) Terminate connections to the target DB
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid();
                    """,
                    (db_name,),
                )
                # 2) Drop the database
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}";')
                logger.info(f"[pytest teardown] Dropped test database: {db_name}")


def _create_test_database():
    """Ensures the existence of a test database for use during testing.

    This function connects to the PostgreSQL server, checks if the test database
    specified in the `TEST_DB_URL` already exists, and creates it if it does not.
    It is intended to be used as part of the pytest setup process.

    Notes
    -----
    - The function assumes that the `TEST_DB_URL` environment variable or constant
      contains the connection string for the test database.
    - The function requires the `psycopg` library for PostgreSQL database interaction.
    - The connection is made to the default "postgres" database to perform the check
      and creation of the test database.

    Raises
    ------
    psycopg.OperationalError
        If there is an issue connecting to the PostgreSQL server.
    psycopg.DatabaseError
        If there is an issue executing the SQL commands.

    Examples
    --------
    >>> _create_test_database()
    [pytest setup] Created database: test_db_name
    """
    db_name, user, password, _, _ = _parse_db_url(TEST_DB_URL)

    conn = psycopg.connect(
        dbname="postgres",
        user=user,
        password=password,
        host="localhost",
        autocommit=True,
    )
    cur = conn.cursor()

    # Check if test DB already exists
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{db_name}"')
        logger.info(f"[pytest setup] Created test database: {db_name}")
    else:
        logger.info(f"[pytest setup] Using existing test database: {db_name}")

    cur.close()
    conn.close()


def _parse_db_url(db_url: str) -> tuple[str, str | None, str | None, str, int]:
    """Parses a database URL into its components.

    Parameters
    ----------
    db_url : str
        The database URL to parse.
    Returns
    -------
    tuple[str, str | None, str | None, str, int]
        A tuple containing the database name, user, password, host, and port.
    """
    parsed = urlparse(db_url)

    db_name = parsed.path.lstrip("/")
    user = parsed.username
    password = parsed.password
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    return db_name, user, password, host, port


def _run_migrations():
    """Runs Alembic migrations to set up the database schema for testing.

    This function configures Alembic to use the test database URL and
    applies all migrations to ensure the database schema is up-to-date
    before running tests.
    """
    alembic_cfg = Config(ALEMBIC_INI_PATH)

    # Inject test DB URL dynamically into Alembic env.
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)

    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="function")
def client(db: Session):
    """Sets up a FastAPI TestClient with a database dependency override.

    This fixture overrides the `get_database_session` dependency used in FastAPI
    routes to inject a test database session instead of the production database.
    This ensures that the application uses the `earthframe_test` database
    during tests, isolating test data from production data.

    Parameters
    ----------
    db : Session
        A SQLAlchemy session object connected to the test database.

    Yields
    ------
    TestClient
        A FastAPI TestClient instance configured to use the test database.

    Notes
    -----
    - The `get_database_session` dependency is overridden to yield the provided test
      database session.
    - After the test client is used, the dependency overrides are cleared
      and the test database session is closed.
    """

    def override_get_database_session():
        try:
            # Do not close the session here; the db fixture finalizer will
            # handle closing and rolling back the transaction/savepoint.
            yield db
        finally:
            pass

    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
