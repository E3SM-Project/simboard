"""Component-set migration preserves values and refuses lossy downgrades."""

from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import engine

migration = import_module(
    "migrations.versions.20261023_010000_fix_component_set_metadata"
)


def test_component_set_migration_preserves_values_and_guards_downgrade():
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TEMP TABLE executions (
                id integer PRIMARY KEY,
                compset varchar(120) NOT NULL,
                compset_alias text NOT NULL
            ) ON COMMIT DROP
        """)
        )
        connection.execute(
            text("INSERT INTO executions VALUES (1, 'old-alias', 'old-long-name')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(
                text("SELECT compset_long_name, compset_alias FROM executions")
            ).one() == ("old-alias", "old-long-name")
            for long_name, alias in [("x" * 121, "alias"), ("name", None)]:
                with connection.begin_nested() as savepoint:
                    connection.execute(
                        text(
                            "UPDATE executions SET compset_long_name=:name, compset_alias=:alias"
                        ),
                        {"name": long_name, "alias": alias},
                    )
                    with pytest.raises(
                        ValueError, match="explicit operator resolution"
                    ):
                        migration.downgrade()
                    savepoint.rollback()
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text("UPDATE executions SET compset_long_name=NULL")
                    )
            migration.downgrade()
            assert connection.execute(
                text("SELECT compset, compset_alias FROM executions")
            ).one() == ("old-alias", "old-long-name")
