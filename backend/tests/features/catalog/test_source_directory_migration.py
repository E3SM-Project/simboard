"""Source-directory migration upgrade/downgrade on the disposable test database."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine


def test_source_directory_migration_is_reversible():
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.downgrade(config, "20260915_010000")
    try:
        assert not inspect(engine).has_table("source_directories")
        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert {
            column["name"] for column in inspector.get_columns("source_directories")
        } == {
            "id",
            "case_id",
            "execution_id",
            "kind",
            "path",
        }
        indexes = inspector.get_indexes("source_directories")
        assert {index["name"] for index in indexes if index["unique"]} == {
            "uq_source_directories_case",
            "uq_source_directories_execution",
        }
        assert all(
            fk["options"].get("ondelete") == "CASCADE"
            for fk in inspector.get_foreign_keys("source_directories")
        )
        command.downgrade(config, "20260915_010000")
        assert not inspect(engine).has_table("source_directories")
    finally:
        command.upgrade(config, "head")
