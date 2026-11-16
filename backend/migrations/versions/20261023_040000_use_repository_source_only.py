"""Use one authoritative repository source instead of a stored browser URL.

Revision ID: 20261023_040000
Revises: 20261023_020000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_040000"
down_revision = "20261023_020000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "executions",
        "git_repository_url",
        new_column_name="git_repository_source",
        existing_type=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "executions",
        "git_repository_source",
        new_column_name="git_repository_url",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
