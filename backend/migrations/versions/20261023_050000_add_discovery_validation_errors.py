"""Store field-aware execution discovery validation errors.

Revision ID: 20261023_050000
Revises: 20261023_040000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261023_050000"
down_revision = "20261023_040000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_discovery_results",
        sa.Column("errors", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("execution_discovery_results", "errors")
