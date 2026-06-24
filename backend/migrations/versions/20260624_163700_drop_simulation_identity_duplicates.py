"""Drop duplicated machine and HPC identity fields from simulations.

Revision ID: 20260624_163700
Revises: 20260624_120000
Create Date: 2026-06-24 16:37:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "20260624_163700"
down_revision: Union[str, Sequence[str], None] = "20260624_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop simulation-owned case identity duplicates."""
    op.drop_constraint(
        op.f("fk_simulations_machine_id_machines"),
        "simulations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_simulations_machine_id"), table_name="simulations")
    op.drop_column("simulations", "machine_id")
    op.drop_column("simulations", "hpc_username")


def downgrade() -> None:
    """Restore duplicated simulation identity fields from authoritative cases."""
    op.add_column(
        "simulations",
        sa.Column("hpc_username", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("machine_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE simulations s
        SET machine_id = c.machine_id,
            hpc_username = c.hpc_username
        FROM cases c
        WHERE c.id = s.case_id
        """
    )
    op.alter_column("simulations", "machine_id", nullable=False)
    op.create_index(
        op.f("ix_simulations_machine_id"),
        "simulations",
        ["machine_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_simulations_machine_id_machines"),
        "simulations",
        "machines",
        ["machine_id"],
        ["id"],
    )
