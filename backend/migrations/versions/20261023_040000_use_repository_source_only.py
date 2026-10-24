"""Use one authoritative repository source instead of a stored browser URL.

Revision ID: 20261023_040000
Revises: 20261023_030000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_040000"
down_revision = "20261023_030000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE executions SET git_repository_source = git_repository_url "
            "WHERE git_repository_source IS NULL"
        )
    )
    op.drop_column("executions", "git_repository_url")


def downgrade() -> None:
    # Sources remain authoritative. Non-HTTP sources have no legacy browser URL.
    op.add_column(
        "executions", sa.Column("git_repository_url", sa.Text(), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE executions SET git_repository_url = git_repository_source "
            "WHERE git_repository_source LIKE 'http://%' "
            "OR git_repository_source LIKE 'https://%'"
        )
    )
