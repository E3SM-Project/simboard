"""Repository provenance migration on the disposable test database."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine


def test_repository_source_migration_is_reversible():
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.downgrade(config, "20261023_010000")
    try:
        assert "git_repository_source" not in {
            column["name"] for column in inspect(engine).get_columns("executions")
        }
        command.upgrade(config, "head")
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("executions")
        }
        assert columns["git_repository_source"]["nullable"]
        command.downgrade(config, "20261023_010000")
        assert "git_repository_source" not in {
            column["name"] for column in inspect(engine).get_columns("executions")
        }
    finally:
        command.upgrade(config, "head")
