"""Preserve original repository provenance separately from its web URL.

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
    op.add_column(
        "executions", sa.Column("git_repository_source", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("executions", "git_repository_source")
