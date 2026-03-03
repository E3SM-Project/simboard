"""Add run_config_deltas column to simulations table

Revision ID: 20260303_000000
Revises: 20260219_000000
Create Date: 2026-03-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "20260303_000000"
down_revision: Union[str, Sequence[str], None] = "20260219_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add run_config_deltas column and migrate data from extra."""
    # Add the new nullable JSONB column
    op.add_column(
        "simulations",
        sa.Column("run_config_deltas", JSONB, nullable=True),
    )

    # Migrate existing data: copy extra->'run_config_deltas' into the
    # new column and remove the key from extra.
    op.execute(
        """
        UPDATE simulations
        SET run_config_deltas = extra->'run_config_deltas',
            extra = extra - 'run_config_deltas'
        WHERE extra ? 'run_config_deltas'
        """
    )


def downgrade() -> None:
    """Move run_config_deltas back into extra and drop the column."""
    # Move non-null column data back into extra['run_config_deltas']
    op.execute(
        """
        UPDATE simulations
        SET extra = jsonb_set(
            COALESCE(extra, '{}'::jsonb),
            '{run_config_deltas}',
            run_config_deltas
        )
        WHERE run_config_deltas IS NOT NULL
        """
    )

    op.drop_column("simulations", "run_config_deltas")
