from datetime import date
from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import engine

migration = import_module(
    "migrations.versions.20261023_000000_store_model_dates_as_strings"
)


def test_model_date_migration_preserves_dates_and_guards_year_zero_downgrade():
    # A temporary table isolates the migration's data conversions from other tests.
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TEMP TABLE executions (
                id integer PRIMARY KEY,
                simulation_start_date date NOT NULL,
                simulation_end_date date
            ) ON COMMIT DROP
        """)
        )
        connection.execute(text("SET LOCAL DateStyle TO 'SQL, DMY'"))
        connection.execute(
            text("""
            INSERT INTO executions VALUES
                (1, DATE '0001-01-02', DATE '9999-12-31'),
                (2, DATE '2019-08-01', NULL)
        """)
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("""
                SELECT simulation_start_date, simulation_end_date
                FROM executions ORDER BY id
            """)
            ).all() == [("0001-01-02", "9999-12-31"), ("2019-08-01", None)]

            for column in ("simulation_start_date", "simulation_end_date"):
                with connection.begin_nested() as savepoint:
                    connection.execute(
                        text(f"""
                        UPDATE executions SET {column} = '0000-01-02' WHERE id = 1
                    """)
                    )
                    with pytest.raises(DBAPIError, match="year-zero records exist"):
                        with connection.begin_nested():
                            migration.downgrade()
                    savepoint.rollback()

            migration.downgrade()
            assert connection.execute(
                text("""
                SELECT simulation_start_date, simulation_end_date
                FROM executions ORDER BY id
            """)
            ).all() == [(date(1, 1, 2), date(9999, 12, 31)), (date(2019, 8, 1), None)]


@pytest.mark.parametrize("value", ["0001-01-01 BC", "10000-01-01", "infinity"])
def test_model_date_migration_rejects_unrepresentable_existing_dates(value):
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TEMP TABLE executions (
                simulation_start_date date NOT NULL,
                simulation_end_date date
            ) ON COMMIT DROP
        """)
        )
        connection.execute(
            text("INSERT INTO executions VALUES (CAST(:value AS date), NULL)"),
            {"value": value},
        )
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(DBAPIError, match="require explicit conversion"):
                with connection.begin_nested():
                    migration.upgrade()
