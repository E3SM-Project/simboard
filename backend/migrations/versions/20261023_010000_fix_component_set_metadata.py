"""Name component-set metadata explicitly and allow missing aliases.

Revision ID: 20261023_010000
Revises: 20261023_000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_010000"
down_revision = "20261023_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve existing values for the separate, provenance-based repair.
    op.alter_column(
        "executions",
        "compset",
        new_column_name="compset_long_name",
        existing_type=sa.String(120),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "executions", "compset_alias", existing_type=sa.Text(), nullable=True
    )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM executions "
            "WHERE compset_alias IS NULL OR length(compset_long_name) > 120)"
        )
    ).scalar_one()
    if incompatible:
        raise ValueError(
            "Cannot downgrade component-set metadata: NULL aliases or long names "
            "over 120 characters require explicit operator resolution."
        )
    op.alter_column(
        "executions", "compset_alias", existing_type=sa.Text(), nullable=False
    )
    op.alter_column(
        "executions",
        "compset_long_name",
        new_column_name="compset",
        existing_type=sa.Text(),
        type_=sa.String(120),
        existing_nullable=False,
    )
