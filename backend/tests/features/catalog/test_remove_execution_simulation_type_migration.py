from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine

PREVIOUS_REVISION = "20260915_000000"
MIGRATION_REVISION = "20260915_010000"


def _execution_columns() -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("executions")}


def _execution_column(name: str) -> dict:
    return next(
        column
        for column in inspect(engine).get_columns("executions")
        if column["name"] == name
    )


def test_execution_simulation_type_migration_is_structurally_reversible() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    try:
        assert "simulation_type" in _execution_columns()

        command.upgrade(alembic_config, MIGRATION_REVISION)
        assert "simulation_type" not in _execution_columns()

        command.downgrade(alembic_config, PREVIOUS_REVISION)
        assert "simulation_type" in _execution_columns()
        restored_column = _execution_column("simulation_type")
        assert restored_column["nullable"] is False
        assert "unknown" in (restored_column["default"] or "")
    finally:
        command.upgrade(alembic_config, "head")
