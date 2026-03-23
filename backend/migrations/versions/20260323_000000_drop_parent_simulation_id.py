"""Drop parent_simulation_id from simulations.

Revision ID: 20260323_000000
Revises: 20260319_000000
Create Date: 2026-03-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260323_000000"
down_revision: Union[str, Sequence[str], None] = "20260319_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the obsolete self-referential parent simulation column."""
    op.drop_constraint(
        op.f("fk_simulations_parent_simulation_id_simulations"),
        "simulations",
        type_="foreignkey",
    )
    op.drop_column("simulations", "parent_simulation_id")


def downgrade() -> None:
    """Restore the parent simulation column and self-referential foreign key."""
    op.add_column(
        "simulations",
        sa.Column("parent_simulation_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_simulations_parent_simulation_id_simulations"),
        "simulations",
        "simulations",
        ["parent_simulation_id"],
        ["id"],
    )
