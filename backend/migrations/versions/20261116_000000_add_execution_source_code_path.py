"""Add execution source-code paths from SRCROOT.

Revision ID: 20261116_000000
Revises: 20261112_020000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261116_000000"
down_revision = "20261112_020000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("source_code_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("executions", "source_code_path")
