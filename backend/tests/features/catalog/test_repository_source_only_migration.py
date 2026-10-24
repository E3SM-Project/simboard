"""Source-only migration retains observed provenance and legacy fallback values."""

from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.conftest import engine

migration = import_module(
    "migrations.versions.20261023_040000_use_repository_source_only"
)


def test_repository_source_only_migration_preserves_values():
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TEMP TABLE executions (
                id integer PRIMARY KEY,
                git_repository_source text,
                git_repository_url text
            ) ON COMMIT DROP
        """)
        )
        connection.execute(
            text("""
            INSERT INTO executions VALUES
            (1, 'ssh://git@github.com/owner/repo', 'https://github.com/owner/repo'),
            (2, NULL, 'https://example.com/repo'),
            (3, '/local/repo', NULL),
            (4, NULL, NULL)
        """)
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("SELECT git_repository_source FROM executions ORDER BY id")
            ).scalars().all() == [
                "ssh://git@github.com/owner/repo",
                "https://example.com/repo",
                "/local/repo",
                None,
            ]
            migration.downgrade()
            assert connection.execute(
                text("SELECT git_repository_url FROM executions ORDER BY id")
            ).scalars().all() == [None, "https://example.com/repo", None, None]
            migration.upgrade()
