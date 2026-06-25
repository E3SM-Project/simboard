"""Add case-level shared metadata fields.

Revision ID: 20260625_120000
Revises: 20260624_163700
Create Date: 2026-06-25 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260625_120000"
down_revision: Union[str, Sequence[str], None] = "20260624_163700"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add shared editable case metadata columns."""
    op.add_column("cases", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("key_features", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("known_issues", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("notes_markdown", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove shared editable case metadata columns."""
    op.drop_column("cases", "notes_markdown")
    op.drop_column("cases", "known_issues")
    op.drop_column("cases", "key_features")
    op.drop_column("cases", "description")
