"""Grid migration preserves values and refuses lossy downgrades."""

from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import engine

migration = import_module("migrations.versions.20261023_020000_fix_grid_metadata")


def test_grid_migration_preserves_values_and_guards_downgrade():
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TEMP TABLE executions (
                id integer PRIMARY KEY,
                grid_name text NOT NULL,
                grid_resolution text NOT NULL
            ) ON COMMIT DROP
        """)
        )
        connection.execute(
            text("INSERT INTO executions VALUES (1, 'old-alias', 'old-spec')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("SELECT grid_alias, grid_long_name FROM executions")
            ).one() == ("old-alias", "old-spec")
            with connection.begin_nested() as savepoint:
                connection.execute(text("UPDATE executions SET grid_alias=NULL"))
                with pytest.raises(ValueError, match="explicit operator resolution"):
                    migration.downgrade()
                savepoint.rollback()
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text("UPDATE executions SET grid_long_name=NULL")
                    )
            migration.downgrade()
            assert connection.execute(
                text("SELECT grid_name, grid_resolution FROM executions")
            ).one() == ("old-alias", "old-spec")
