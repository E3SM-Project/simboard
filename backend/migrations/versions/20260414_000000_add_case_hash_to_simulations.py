"""Add case_hash column to simulations.

Revision ID: 20260414_000000
Revises: 20260331_000000
Create Date: 2026-03-30 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260414_000000"
down_revision: Union[str, Sequence[str], None] = "20260331_000000"
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
