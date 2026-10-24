"""Name grid metadata explicitly and allow missing aliases.

Revision ID: 20261023_020000
Revises: 20261023_010000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_020000"
down_revision = "20261023_010000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve stored values; only source-backed repair can establish correctness.
    op.alter_column(
        "executions",
        "grid_name",
        new_column_name="grid_alias",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "executions",
        "grid_resolution",
        new_column_name="grid_long_name",
        existing_type=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM executions WHERE grid_alias IS NULL)")
    ).scalar_one():
        raise ValueError(
            "Cannot downgrade grid metadata: NULL aliases require explicit operator resolution."
        )
    op.alter_column(
        "executions",
        "grid_alias",
        new_column_name="grid_name",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "executions",
        "grid_long_name",
        new_column_name="grid_resolution",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
