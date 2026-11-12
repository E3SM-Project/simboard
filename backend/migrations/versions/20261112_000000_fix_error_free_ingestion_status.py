"""Correct failed ingestion audit records that have no errors.

Revision ID: 20261112_000000
Revises: 20261023_050000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261112_000000"
down_revision = "20261023_050000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ingestions SET status = 'success' "
            "WHERE status = 'failed' AND error_count = 0"
        )
    )


def downgrade() -> None:
    # Corrected records cannot be distinguished from other successful ingestions.
    pass
