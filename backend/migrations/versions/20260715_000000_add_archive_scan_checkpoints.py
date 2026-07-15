"""Add database-backed archive scan checkpoints.

Revision ID: 20260715_000000
Revises: 20260714_000000
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_000000"
down_revision: Union[str, Sequence[str], None] = "20260714_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create completed immutable-snapshot storage."""
    op.create_table(
        "archive_scan_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("archive_name", sa.Text(), nullable=False),
        sa.Column("archive_month", sa.String(length=7), nullable=False),
        sa.Column("snapshot_name", sa.Text(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "machine_id",
            "archive_name",
            "archive_month",
            "snapshot_name",
            name="uq_archive_scan_checkpoint_identity",
        ),
    )
    op.create_index(
        "ix_archive_scan_checkpoints_lookup",
        "archive_scan_checkpoints",
        ["machine_id", "archive_name", "archive_month"],
    )


def downgrade() -> None:
    """Drop completed immutable-snapshot storage."""
    op.drop_index(
        "ix_archive_scan_checkpoints_lookup",
        table_name="archive_scan_checkpoints",
    )
    op.drop_table("archive_scan_checkpoints")
