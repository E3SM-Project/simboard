"""Add sites as parent records for machines.

Revision ID: 20260721_000000
Revises: 20260715_000000
Create Date: 2026-07-21 00:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_000000"
down_revision: Union[str, Sequence[str], None] = "20260715_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sites and replace machine site names with foreign keys."""
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sites")),
    )
    op.create_index(op.f("ix_sites_name"), "sites", ["name"], unique=True)

    connection = op.get_bind()
    machine_sites = list(
        connection.execute(
            sa.text("SELECT DISTINCT site FROM machines ORDER BY site")
        ).scalars()
    )
    sites = sa.table(
        "sites",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=200)),
    )
    site_ids = {site_name: uuid4() for site_name in machine_sites}
    if site_ids:
        op.bulk_insert(
            sites,
            [
                {"id": site_id, "name": site_name}
                for site_name, site_id in site_ids.items()
            ],
        )

    op.add_column(
        "machines",
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    for site_name, site_id in site_ids.items():
        connection.execute(
            sa.text("UPDATE machines SET site_id = :site_id WHERE site = :site_name"),
            {"site_id": site_id, "site_name": site_name},
        )

    missing_site_count = connection.execute(
        sa.text("SELECT count(*) FROM machines WHERE site_id IS NULL")
    ).scalar_one()
    if missing_site_count:
        raise RuntimeError(
            f"Cannot migrate machines because {missing_site_count} site links are missing"
        )

    op.alter_column("machines", "site_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_machines_site_id_sites"),
        "machines",
        "sites",
        ["site_id"],
        ["id"],
    )
    op.create_index(op.f("ix_machines_site_id"), "machines", ["site_id"], unique=False)
    op.drop_column("machines", "site")


def downgrade() -> None:
    """Restore machine site names and remove site records."""
    connection = op.get_bind()
    op.add_column("machines", sa.Column("site", sa.String(length=200), nullable=True))
    connection.execute(
        sa.text(
            """
            UPDATE machines
            SET site = sites.name
            FROM sites
            WHERE machines.site_id = sites.id
            """
        )
    )

    missing_site_count = connection.execute(
        sa.text("SELECT count(*) FROM machines WHERE site IS NULL")
    ).scalar_one()
    if missing_site_count:
        raise RuntimeError(
            f"Cannot downgrade sites because {missing_site_count} names are missing"
        )

    op.alter_column("machines", "site", nullable=False)
    op.drop_index(op.f("ix_machines_site_id"), table_name="machines")
    op.drop_constraint(
        op.f("fk_machines_site_id_sites"), "machines", type_="foreignkey"
    )
    op.drop_column("machines", "site_id")
    op.drop_index(op.f("ix_sites_name"), table_name="sites")
    op.drop_table("sites")
