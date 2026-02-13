"""Add ingestion audit model

Revision ID: 0ac241ea9faf
Revises: 4ab61b2fce04
Create Date: 2026-02-13 15:02:26.525159

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0ac241ea9faf"
down_revision: Union[str, Sequence[str], None] = "4ab61b2fce04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestions_id"), "ingestions", ["id"], unique=False)
    op.create_index(
        op.f("ix_ingestions_triggered_by"), "ingestions", ["triggered_by"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ingestions_triggered_by"), table_name="ingestions")
    op.drop_index(op.f("ix_ingestions_id"), table_name="ingestions")
    op.drop_table("ingestions")
