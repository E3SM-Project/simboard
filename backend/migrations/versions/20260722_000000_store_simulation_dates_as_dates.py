"""Store simulation dates as calendar dates.

Revision ID: 20260722_000000
Revises: 20260721_120000
Create Date: 2026-07-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_000000"
down_revision: Union[str, Sequence[str], None] = "20260721_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert model timeline timestamps to timezone-neutral calendar dates."""
    op.alter_column(
        "simulations",
        "simulation_start_date",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Date(),
        existing_nullable=False,
        postgresql_using="(simulation_start_date AT TIME ZONE 'UTC')::date",
    )
    op.alter_column(
        "simulations",
        "simulation_end_date",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Date(),
        existing_nullable=True,
        postgresql_using="(simulation_end_date AT TIME ZONE 'UTC')::date",
    )


def downgrade() -> None:
    """Restore model timeline values as midnight UTC timestamps."""
    op.alter_column(
        "simulations",
        "simulation_start_date",
        existing_type=sa.Date(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="simulation_start_date::timestamp AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "simulations",
        "simulation_end_date",
        existing_type=sa.Date(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="simulation_end_date::timestamp AT TIME ZONE 'UTC'",
    )
