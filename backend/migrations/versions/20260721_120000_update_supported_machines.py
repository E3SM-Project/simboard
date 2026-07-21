"""Update supported machines and preserve execution compute type.

Revision ID: 20260721_120000
Revises: 20260721_000000
Create Date: 2026-07-21 12:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_120000"
down_revision: Union[str, Sequence[str], None] = "20260721_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_or_create_site_id(connection: sa.Connection, site_name: str) -> UUID:
    site_id = connection.execute(
        sa.text("SELECT id FROM sites WHERE name = :name"), {"name": site_name}
    ).scalar_one_or_none()
    if site_id is not None:
        return site_id

    site_id = uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO sites (id, name, created_at, updated_at)
            VALUES (:id, :name, :now, :now)
            """
        ),
        {"id": site_id, "name": site_name, "now": datetime.now(timezone.utc)},
    )
    return site_id


def _assert_machines_unreferenced(
    connection: sa.Connection, machine_names: tuple[str, ...]
) -> None:
    referenced_names = list(
        connection.execute(
            sa.text(
                """
                SELECT DISTINCT machines.name
                FROM machines
                JOIN cases ON cases.machine_id = machines.id
                WHERE machines.name IN :machine_names
                ORDER BY machines.name
                """
            ).bindparams(sa.bindparam("machine_names", expanding=True)),
            {"machine_names": machine_names},
        ).scalars()
    )
    if referenced_names:
        joined_names = ", ".join(referenced_names)
        raise RuntimeError(
            f"Cannot remove machines referenced by existing cases: {joined_names}"
        )


def upgrade() -> None:
    """Add compute type, seed NERSC machines, and remove Anvil."""
    op.add_column(
        "simulations", sa.Column("compute_type", sa.String(length=3), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_simulations_compute_type"),
        "simulations",
        "compute_type IS NULL OR compute_type IN ('cpu', 'gpu')",
    )

    connection = op.get_bind()
    nersc_site_id = _get_or_create_site_id(connection, "NERSC")
    now = datetime.now(timezone.utc)
    machines = sa.table(
        "machines",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=200)),
        sa.column("site_id", postgresql.UUID(as_uuid=True)),
        sa.column("architecture", sa.String(length=100)),
        sa.column("scheduler", sa.String(length=100)),
        sa.column("gpu", sa.Boolean()),
        sa.column("notes", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        machines,
        [
            {
                "id": uuid4(),
                "name": "muller",
                "site_id": nersc_site_id,
                "architecture": "NERSC internal CPU/GPU test system",
                "scheduler": "slurm",
                "gpu": True,
                "notes": "Canonical machine for muller-cpu and muller-gpu.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid4(),
                "name": "alvarez",
                "site_id": nersc_site_id,
                "architecture": "AMD EPYC 7713 CPU and GPU test system",
                "scheduler": "slurm",
                "gpu": True,
                "notes": "Canonical machine for alvarez-cpu and alvarez-gpu.",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    lcrc_site_id = _get_or_create_site_id(connection, "LCRC")
    connection.execute(
        sa.text("UPDATE machines SET site_id = :site_id WHERE name = 'chrysalis'"),
        {"site_id": lcrc_site_id},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM sites
            WHERE name = 'ANL (LCRC)'
              AND NOT EXISTS (
                  SELECT 1 FROM machines WHERE machines.site_id = sites.id
              )
            """
        )
    )
    _assert_machines_unreferenced(connection, ("anvil",))
    connection.execute(sa.text("DELETE FROM machines WHERE name = 'anvil'"))
    connection.execute(
        sa.text(
            """
            DELETE FROM sites
            WHERE name = 'ANL'
              AND NOT EXISTS (
                  SELECT 1 FROM machines WHERE machines.site_id = sites.id
              )
            """
        )
    )


def downgrade() -> None:
    """Restore previous supported-machine data and remove compute type."""
    connection = op.get_bind()
    _assert_machines_unreferenced(connection, ("muller", "alvarez"))
    connection.execute(
        sa.text("DELETE FROM machines WHERE name IN ('muller', 'alvarez')")
    )

    anl_site_id = _get_or_create_site_id(connection, "ANL")
    now = datetime.now(timezone.utc)
    connection.execute(
        sa.text(
            """
            INSERT INTO machines (
                id, name, site_id, architecture, scheduler, gpu, notes,
                created_at, updated_at
            )
            VALUES (
                :id, 'anvil', :site_id, 'x86_64 CPU cluster', 'slurm', false,
                'E3SM-dedicated machine at ANL (historical/limited availability).',
                :now, :now
            )
            """
        ),
        {"id": uuid4(), "site_id": anl_site_id, "now": now},
    )
    legacy_lcrc_site_id = _get_or_create_site_id(connection, "ANL (LCRC)")
    connection.execute(
        sa.text("UPDATE machines SET site_id = :site_id WHERE name = 'chrysalis'"),
        {"site_id": legacy_lcrc_site_id},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM sites
            WHERE name = 'LCRC'
              AND NOT EXISTS (
                  SELECT 1 FROM machines WHERE machines.site_id = sites.id
              )
            """
        )
    )

    op.drop_constraint(
        op.f("ck_simulations_compute_type"),
        "simulations",
        type_="check",
    )
    op.drop_column("simulations", "compute_type")
