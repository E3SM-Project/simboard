"""Drop simulation name column

The ``Simulation.name`` field duplicated ``Case.name`` and is no longer
part of the data model.  Identity is now split between ``Case.name``
(experiment) and ``Simulation.execution_id`` (execution).

Revision ID: 20260304_000000
Revises: be6a6cb6e825
Create Date: 2026-03-04 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260304_000000"
down_revision: Union[str, Sequence[str], None] = "be6a6cb6e825"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the ``name`` column and its index from ``simulations``."""
    op.drop_index("ix_simulations_name", table_name="simulations")
    op.drop_column("simulations", "name")


def downgrade() -> None:
    """Re-add the ``name`` column.

    Backfills from the associated ``cases.name`` via ``case_id``.
    """
    op.add_column(
        "simulations",
        sa.Column("name", sa.String(200), nullable=True),
    )

    # Backfill name from cases.name
    op.execute(
        sa.text(
            "UPDATE simulations SET name = c.name "
            "FROM cases c WHERE simulations.case_id = c.id"
        )
    )

    # Make non-null after backfill
    op.alter_column("simulations", "name", nullable=False)

    op.create_index("ix_simulations_name", "simulations", ["name"])
