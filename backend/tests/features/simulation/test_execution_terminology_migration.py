from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine

PREVIOUS_REVISION = "20260722_000000"


def test_execution_terminology_migration_preserves_schema_data_and_behavior() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    user_id = uuid4()
    case_id = uuid4()
    ingestion_id = uuid4()
    execution_id = uuid4()
    artifact_id = uuid4()
    link_id = uuid4()

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    try:
        with engine.begin() as connection:
            machine_id = connection.execute(
                text("SELECT id FROM machines ORDER BY name LIMIT 1")
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, email, hashed_password, is_active, is_superuser,
                        is_verified, role, has_verified_e3sm_membership
                    ) VALUES (
                        :id, :email, NULL, true, false, true, 'USER', false
                    )
                    """
                ),
                {
                    "id": user_id,
                    "email": f"execution-migration-{user_id}@example.com",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO cases (id, name, machine_id, hpc_username)
                    VALUES (:id, :name, :machine_id, 'migration-user')
                    """
                ),
                {
                    "id": case_id,
                    "name": f"execution-migration-{case_id}",
                    "machine_id": machine_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ingestions (
                        id, source_type, source_reference, machine_id,
                        triggered_by, created_at, status, created_count,
                        duplicate_count, error_count
                    ) VALUES (
                        :id, 'browser_upload', 'execution-migration', :machine_id,
                        :user_id, now(), 'success', 1, 0, 0
                    )
                    """
                ),
                {
                    "id": ingestion_id,
                    "machine_id": machine_id,
                    "user_id": user_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO simulations (
                        id, case_id, execution_id, compset, compset_alias,
                        grid_name, grid_resolution, simulation_type, status,
                        initialization_type, simulation_start_date, created_by,
                        last_updated_by, ingestion_id, extra
                    ) VALUES (
                        :id, :case_id, 'migration-execution', 'AQUAPLANET',
                        'QPC4', 'f19_f19', '1.9x2.5', 'experimental',
                        'created', 'startup', DATE '2023-01-01', :user_id,
                        :user_id, :ingestion_id, '{}'::jsonb
                    )
                    """
                ),
                {
                    "id": execution_id,
                    "case_id": case_id,
                    "user_id": user_id,
                    "ingestion_id": ingestion_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO artifacts (id, simulation_id, kind, uri)
                    VALUES (:id, :simulation_id, 'output', 'file:///output')
                    """
                ),
                {"id": artifact_id, "simulation_id": execution_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO external_links (
                        id, simulation_id, kind, url, label
                    ) VALUES (
                        :id, :simulation_id, 'diagnostic',
                        'https://example.com/diagnostic', 'Diagnostic'
                    )
                    """
                ),
                {"id": link_id, "simulation_id": execution_id},
            )

        command.upgrade(alembic_config, "head")

        inspector = inspect(engine)
        assert "executions" in inspector.get_table_names()
        assert "simulations" not in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns("artifacts")} >= {
            "execution_id"
        }
        assert {
            column["name"] for column in inspector.get_columns("external_links")
        } >= {"execution_id"}
        assert inspector.get_pk_constraint("executions")["name"] == "pk_executions"
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("executions")
        } >= {"uq_executions_case_id_execution_id"}
        assert {
            constraint["name"]
            for constraint in inspector.get_check_constraints("executions")
        } >= {"ck_executions_compute_type"}
        assert {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("artifacts")
        } >= {"fk_artifacts_execution_id_executions"}
        assert {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("external_links")
        } >= {"fk_external_links_execution_id_executions"}
        assert {index["name"] for index in inspector.get_indexes("executions")} >= {
            "ix_executions_case_id",
            "ix_executions_execution_id",
            "ix_executions_status",
        }
        assert {index["name"] for index in inspector.get_indexes("artifacts")} >= {
            "ix_artifacts_execution_id"
        }

        with engine.connect() as connection:
            migrated_row = connection.execute(
                text(
                    """
                    SELECT e.id, a.id, l.id
                    FROM executions AS e
                    JOIN artifacts AS a ON a.execution_id = e.id
                    JOIN external_links AS l ON l.execution_id = e.id
                    WHERE e.id = :id
                    """
                ),
                {"id": execution_id},
            ).one()
        assert migrated_row == (execution_id, artifact_id, link_id)

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO executions (
                            id, case_id, execution_id, compset, compset_alias,
                            grid_name, grid_resolution, simulation_type, status,
                            initialization_type, simulation_start_date, created_by,
                            last_updated_by, ingestion_id, extra
                        )
                        SELECT
                            :id, case_id, execution_id, compset, compset_alias,
                            grid_name, grid_resolution, simulation_type, status,
                            initialization_type, simulation_start_date, created_by,
                            last_updated_by, ingestion_id, extra
                        FROM executions WHERE id = :source_id
                        """
                    ),
                    {"id": uuid4(), "source_id": execution_id},
                )

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text("DELETE FROM executions WHERE id = :id"),
                    {"id": execution_id},
                )
                assert (
                    connection.execute(
                        text("SELECT COUNT(*) FROM artifacts WHERE execution_id = :id"),
                        {"id": execution_id},
                    ).scalar_one()
                    == 0
                )
                assert (
                    connection.execute(
                        text(
                            "SELECT COUNT(*) FROM external_links WHERE execution_id = :id"
                        ),
                        {"id": execution_id},
                    ).scalar_one()
                    == 0
                )
            finally:
                transaction.rollback()

        command.downgrade(alembic_config, PREVIOUS_REVISION)
        downgraded_inspector = inspect(engine)
        assert "simulations" in downgraded_inspector.get_table_names()
        assert "executions" not in downgraded_inspector.get_table_names()
        assert {
            column["name"] for column in downgraded_inspector.get_columns("artifacts")
        } >= {"simulation_id"}
        with engine.connect() as connection:
            downgraded_row = connection.execute(
                text(
                    """
                    SELECT s.id, a.id, l.id
                    FROM simulations AS s
                    JOIN artifacts AS a ON a.simulation_id = s.id
                    JOIN external_links AS l ON l.simulation_id = s.id
                    WHERE s.id = :id
                    """
                ),
                {"id": execution_id},
            ).one()
        assert downgraded_row == (execution_id, artifact_id, link_id)
    finally:
        command.downgrade(alembic_config, PREVIOUS_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM simulations WHERE id = :id"),
                {"id": execution_id},
            )
            connection.execute(
                text("DELETE FROM ingestions WHERE id = :id"),
                {"id": ingestion_id},
            )
            connection.execute(
                text("DELETE FROM cases WHERE id = :id"),
                {"id": case_id},
            )
            connection.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": user_id},
            )
        command.upgrade(alembic_config, "head")
