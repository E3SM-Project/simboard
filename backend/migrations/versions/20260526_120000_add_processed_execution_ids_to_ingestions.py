"""Add processed execution IDs to ingestions.

Revision ID: 20260526_120000
Revises: 20260331_000000
Create Date: 2026-05-26 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260526_120000"
down_revision: Union[str, Sequence[str], None] = "20260331_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist runner execution IDs on ingestion audit rows."""
    op.add_column(
        "ingestions",
        sa.Column(
            "processed_execution_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop persisted runner execution IDs from ingestion audit rows."""
    op.drop_column("ingestions", "processed_execution_ids")
