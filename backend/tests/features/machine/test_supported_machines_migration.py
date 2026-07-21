from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine


def test_supported_machine_migration_state(db: Session) -> None:
    rows = db.execute(
        text(
            """
            SELECT machines.name, sites.name, machines.architecture,
                   machines.scheduler, machines.gpu, machines.notes
            FROM machines
            JOIN sites ON sites.id = machines.site_id
            WHERE machines.name IN ('muller', 'alvarez')
            ORDER BY machines.name
            """
        )
    ).all()

    assert rows == [
        (
            "alvarez",
            "NERSC",
            "AMD EPYC 7713 CPU and GPU test system",
            "slurm",
            True,
            "Canonical machine for alvarez-cpu and alvarez-gpu.",
        ),
        (
            "muller",
            "NERSC",
            "NERSC internal CPU/GPU test system",
            "slurm",
            True,
            "Canonical machine for muller-cpu and muller-gpu.",
        ),
    ]
    assert (
        db.execute(
            text("SELECT count(*) FROM machines WHERE name = 'anvil'")
        ).scalar_one()
        == 0
    )
    assert (
        db.execute(
            text(
                """
            SELECT sites.name
            FROM machines
            JOIN sites ON sites.id = machines.site_id
            WHERE machines.name = 'chrysalis'
            """
            )
        ).scalar_one()
        == "LCRC"
    )

    columns = {
        column["name"] for column in inspect(db.connection()).get_columns("simulations")
    }
    constraints = {
        constraint["name"]
        for constraint in inspect(db.connection()).get_check_constraints("simulations")
    }
    assert "compute_type" in columns
    assert "ck_simulations_compute_type" in constraints


def test_upgrade_refuses_to_remove_referenced_anvil() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    case_id = uuid4()

    command.downgrade(alembic_config, "20260721_000000")
    try:
        with engine.begin() as connection:
            anvil_id = connection.execute(
                text("SELECT id FROM machines WHERE name = 'anvil'")
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO cases (id, name, machine_id, hpc_username)
                    VALUES (:id, 'anvil-migration-guard', :machine_id, 'test-user')
                    """
                ),
                {"id": case_id, "machine_id": anvil_id},
            )

        with pytest.raises(RuntimeError, match="existing cases: anvil"):
            command.upgrade(alembic_config, "head")
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM cases WHERE id = :id"), {"id": case_id}
            )
        command.upgrade(alembic_config, "head")


def test_upgrade_tolerates_existing_supported_machine() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    machine_id = uuid4()

    command.downgrade(alembic_config, "20260721_000000")
    try:
        with engine.begin() as connection:
            nersc_site_id = connection.execute(
                text("SELECT id FROM sites WHERE name = 'NERSC'")
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO machines (
                        id, name, site_id, architecture, scheduler, gpu
                    )
                    VALUES (
                        :id, 'muller', :site_id, 'existing', 'slurm', true
                    )
                    """
                ),
                {"id": machine_id, "site_id": nersc_site_id},
            )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            existing_machine = connection.execute(
                text(
                    """
                    SELECT id, architecture
                    FROM machines
                    WHERE lower(name) = 'muller'
                    """
                )
            ).one()
        assert existing_machine == (machine_id, "existing")
    finally:
        command.downgrade(alembic_config, "20260721_000000")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM machines WHERE id = :id"), {"id": machine_id}
            )
        command.upgrade(alembic_config, "head")


def test_lcrc_migration_preserves_unrelated_existing_site_relationships() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    site_id = uuid4()
    machine_id = uuid4()

    command.downgrade(alembic_config, "20260721_000000")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO sites (id, name) VALUES (:id, 'LCRC')"),
                {"id": site_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO machines (
                        id, name, site_id, architecture, scheduler, gpu
                    )
                    VALUES (
                        :id, 'unrelated-lcrc-machine', :site_id,
                        'x86_64', 'slurm', false
                    )
                    """
                ),
                {"id": machine_id, "site_id": site_id},
            )

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            upgraded_sites = dict(
                connection.execute(
                    text(
                        """
                        SELECT machines.name, machines.site_id
                        FROM machines
                        WHERE machines.name IN ('chrysalis', 'unrelated-lcrc-machine')
                        """
                    )
                ).all()
            )
        assert upgraded_sites == {
            "chrysalis": site_id,
            "unrelated-lcrc-machine": site_id,
        }

        command.downgrade(alembic_config, "20260721_000000")
        with engine.connect() as connection:
            downgraded_sites = dict(
                connection.execute(
                    text(
                        """
                        SELECT machines.name, sites.name
                        FROM machines
                        JOIN sites ON sites.id = machines.site_id
                        WHERE machines.name IN ('chrysalis', 'unrelated-lcrc-machine')
                        """
                    )
                ).all()
            )
        assert downgraded_sites == {
            "chrysalis": "ANL (LCRC)",
            "unrelated-lcrc-machine": "LCRC",
        }

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            reupgraded_site_id = connection.execute(
                text(
                    """
                    SELECT site_id FROM machines
                    WHERE name = 'unrelated-lcrc-machine'
                    """
                )
            ).scalar_one()
        assert reupgraded_site_id == site_id
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM machines WHERE id = :id"), {"id": machine_id}
            )
            connection.execute(
                text(
                    """
                    DELETE FROM sites
                    WHERE id = :id
                      AND NOT EXISTS (
                          SELECT 1 FROM machines WHERE machines.site_id = sites.id
                      )
                    """
                ),
                {"id": site_id},
            )
        command.upgrade(alembic_config, "head")
