"""Discovery validation error storage upgrades and downgrades safely."""

from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.conftest import engine

migration = import_module(
    "migrations.versions.20261023_050000_add_discovery_validation_errors"
)


def test_discovery_error_migration_preserves_existing_outcomes():
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE TEMP TABLE execution_discovery_results (
                    id integer PRIMARY KEY, outcome text
                ) ON COMMIT DROP
            """)
        )
        connection.execute(
            text("INSERT INTO execution_discovery_results VALUES (1, 'accepted')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("SELECT outcome, errors FROM execution_discovery_results")
            ).one() == ("accepted", None)
            connection.execute(
                text("""
                    UPDATE execution_discovery_results SET errors =
                    '[{"field":"grid_long_name","code":"string_type"}]'::jsonb
                """)
            )
            assert connection.execute(
                text("SELECT errors FROM execution_discovery_results")
            ).scalar_one() == [{"field": "grid_long_name", "code": "string_type"}]
            migration.downgrade()
            assert (
                connection.execute(
                    text("SELECT outcome FROM execution_discovery_results")
                ).scalar_one()
                == "accepted"
            )
            migration.upgrade()
