import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.site.models import Site
from tests.conftest import ALEMBIC_INI_PATH, TEST_DB_URL, engine


def test_site_name_is_unique(db: Session) -> None:
    db.add(Site(name="Unique Site"))
    db.commit()
    db.add(Site(name="Unique Site"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_migration_backfills_shared_site_relationships(db: Session) -> None:
    machine_site_names = set(
        db.execute(
            text(
                """
                SELECT sites.name
                FROM machines
                JOIN sites ON sites.id = machines.site_id
                """
            )
        ).scalars()
    )
    site_names = set(db.execute(text("SELECT name FROM sites")).scalars())

    assert machine_site_names == site_names
    assert db.query(Machine).filter(Machine.site_id.is_(None)).count() == 0


def test_migration_downgrade_and_reupgrade_preserves_machine_sites() -> None:
    alembic_config = Config(ALEMBIC_INI_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DB_URL)

    with engine.connect() as connection:
        expected_sites: dict[int, str] = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    """
                    SELECT machines.id, sites.name
                    FROM machines
                    JOIN sites ON sites.id = machines.site_id
                    """
                )
            )
        }

    try:
        command.downgrade(alembic_config, "20260715_000000")

        with engine.connect() as connection:
            columns = {
                column["name"] for column in inspect(connection).get_columns("machines")
            }
            downgraded_sites: dict[int, str] = {
                row[0]: row[1]
                for row in connection.execute(text("SELECT id, site FROM machines"))
            }

        assert "site" in columns
        assert "site_id" not in columns
        assert downgraded_sites == expected_sites
    finally:
        command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        reupgraded_sites: dict[int, str] = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    """
                    SELECT machines.id, sites.name
                    FROM machines
                    JOIN sites ON sites.id = machines.site_id
                    """
                )
            )
        }

    assert reupgraded_sites == expected_sites


def test_multiple_machines_can_share_site(db: Session) -> None:
    site = Site(name="Shared Site")
    first = Machine(
        name="shared-site-one",
        site_record=site,
        architecture="x86_64",
        scheduler="slurm",
        gpu=False,
    )
    second = Machine(
        name="shared-site-two",
        site_record=site,
        architecture="x86_64",
        scheduler="slurm",
        gpu=False,
    )
    db.add_all([first, second])
    db.commit()

    assert first.site_id == second.site_id == site.id
    assert {machine.name for machine in site.machines} == {
        "shared-site-one",
        "shared-site-two",
    }
