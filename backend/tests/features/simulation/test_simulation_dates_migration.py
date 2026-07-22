from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine

PREVIOUS_REVISION = "20260721_120000"


def test_simulation_date_migration_is_timezone_independent_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGOPTIONS", "-c timezone=America/Los_Angeles")
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    user_id = uuid4()
    case_id = uuid4()
    ingestion_id = uuid4()
    simulation_id = uuid4()
    null_end_simulation_id = uuid4()

    command.downgrade(alembic_config, PREVIOUS_REVISION)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET TIME ZONE 'America/Los_Angeles'"))
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
                {"id": user_id, "email": f"date-migration-{user_id}@example.com"},
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
                    "name": f"date-migration-{case_id}",
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
                        :id, 'browser_upload', 'migration-test', :machine_id,
                        :user_id, now(), 'success', 1, 0, 0
                    )
                    """
                ),
                {"id": ingestion_id, "machine_id": machine_id, "user_id": user_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO simulations (
                        id, case_id, execution_id, compset, compset_alias,
                        grid_name, grid_resolution, simulation_type, status,
                        initialization_type, simulation_start_date,
                        simulation_end_date, created_by, last_updated_by,
                        ingestion_id, extra
                    ) VALUES (
                        :id, :case_id, 'migration-execution', 'AQUAPLANET',
                        'QPC4', 'f19_f19', '1.9x2.5', 'experimental',
                        'created', 'startup',
                        TIMESTAMPTZ '2019-08-01 00:00:00+00',
                        TIMESTAMPTZ '2019-09-01 00:00:00+00',
                        :user_id, :user_id, :ingestion_id, '{}'::jsonb
                    )
                    """
                ),
                {
                    "id": simulation_id,
                    "case_id": case_id,
                    "user_id": user_id,
                    "ingestion_id": ingestion_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO simulations (
                        id, case_id, execution_id, compset, compset_alias,
                        grid_name, grid_resolution, simulation_type, status,
                        initialization_type, simulation_start_date,
                        simulation_end_date, created_by, last_updated_by,
                        ingestion_id, extra
                    )
                    SELECT
                        :new_id, case_id, 'migration-null-end', compset,
                        compset_alias, grid_name, grid_resolution,
                        simulation_type, status, initialization_type,
                        simulation_start_date, NULL, created_by,
                        last_updated_by, ingestion_id, extra
                    FROM simulations WHERE id = :source_id
                    """
                ),
                {"new_id": null_end_simulation_id, "source_id": simulation_id},
            )

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            connection.execute(text("SET TIME ZONE 'America/Los_Angeles'"))
            upgraded = connection.execute(
                text(
                    """
                    SELECT simulation_start_date, simulation_end_date
                    FROM simulations WHERE id = :id
                    """
                ),
                {"id": simulation_id},
            ).one()
        assert upgraded == (date(2019, 8, 1), date(2019, 9, 1))
        with engine.connect() as connection:
            null_end_date = connection.execute(
                text("SELECT simulation_end_date FROM simulations WHERE id = :id"),
                {"id": null_end_simulation_id},
            ).scalar_one()
        assert null_end_date is None

        command.downgrade(alembic_config, PREVIOUS_REVISION)
        with engine.connect() as connection:
            connection.execute(text("SET TIME ZONE 'America/Los_Angeles'"))
            downgraded = connection.execute(
                text(
                    """
                    SELECT simulation_start_date, simulation_end_date
                    FROM simulations WHERE id = :id
                    """
                ),
                {"id": simulation_id},
            ).one()
        assert downgraded == (
            datetime(2019, 8, 1, tzinfo=timezone.utc),
            datetime(2019, 9, 1, tzinfo=timezone.utc),
        )
    finally:
        command.downgrade(alembic_config, PREVIOUS_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM simulations WHERE id IN (:id, :null_end_id)"),
                {"id": simulation_id, "null_end_id": null_end_simulation_id},
            )
            connection.execute(
                text("DELETE FROM ingestions WHERE id = :id"), {"id": ingestion_id}
            )
            connection.execute(
                text("DELETE FROM cases WHERE id = :id"), {"id": case_id}
            )
            connection.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": user_id}
            )
        command.upgrade(alembic_config, "head")
