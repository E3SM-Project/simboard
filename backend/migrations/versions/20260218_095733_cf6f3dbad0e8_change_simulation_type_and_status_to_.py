"""Change simulation_type and status to enums

Revision ID: cf6f3dbad0e8
Revises: 3f4960b8c4ba
Create Date: 2026-02-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cf6f3dbad0e8"
down_revision: Union[str, Sequence[str], None] = "3f4960b8c4ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_simulations_status_status_lookup",
        "simulations",
        type_="foreignkey",
    )

    op.alter_column(
        "simulations",
        "simulation_type",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum(
            "unknown",
            "production",
            "experimental",
            "test",
            name="simulation_type_enum",
            native_enum=False,
        ),
        existing_nullable=False,
    )

    op.alter_column(
        "simulations",
        "status",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum(
            "unknown",
            "created",
            "queued",
            "running",
            "failed",
            "completed",
            name="simulation_status_enum",
            native_enum=False,
        ),
        existing_nullable=False,
    )

    op.drop_table("status_lookup")


def downgrade() -> None:
    op.create_table(
        "status_lookup",
        sa.Column("code", sa.VARCHAR(length=50), nullable=False),
        sa.Column("label", sa.VARCHAR(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_status_lookup"),
    )

    op.alter_column(
        "simulations",
        "status",
        existing_type=sa.Enum(
            "unknown",
            "created",
            "queued",
            "running",
            "failed",
            "completed",
            name="simulation_status_enum",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )

    op.alter_column(
        "simulations",
        "simulation_type",
        existing_type=sa.Enum(
            "unknown",
            "production",
            "experimental",
            "test",
            name="simulation_type_enum",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )

    op.create_foreign_key(
        "fk_simulations_status_status_lookup",
        "simulations",
        "status_lookup",
        ["status"],
        ["code"],
    )
