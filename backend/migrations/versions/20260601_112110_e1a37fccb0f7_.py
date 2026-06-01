"""Add case_hash column to simulations.

Revision ID: e1a37fccb0f7
Revises: 20260526_120000
Create Date: 2026-06-01 11:21:10.936484

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a37fccb0f7"
down_revision: Union[str, Sequence[str], None] = "20260526_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable CASE_HASH storage to simulations."""
    op.add_column(
        "simulations",
        sa.Column("case_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove CASE_HASH storage from simulations."""
    op.drop_column("simulations", "case_hash")
