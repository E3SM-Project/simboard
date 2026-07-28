"""Add append-only metadata change history.

Revision ID: 20260728_010000
Revises: 20260728_000000
Create Date: 2026-07-28 01:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_010000"
down_revision: Union[str, Sequence[str], None] = "20260728_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create metadata change history storage."""
    op.create_table(
        "metadata_changes",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("editor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('case', 'execution')",
            name=op.f("ck_metadata_changes_entity_type"),
        ),
        sa.ForeignKeyConstraint(
            ["editor_id"],
            ["users.id"],
            name=op.f("fk_metadata_changes_editor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata_changes")),
    )
    op.create_index(
        "ix_metadata_changes_entity_history",
        "metadata_changes",
        ["entity_type", "entity_id", "changed_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop metadata change history storage."""
    op.drop_index(
        "ix_metadata_changes_entity_history",
        table_name="metadata_changes",
    )
    op.drop_table("metadata_changes")
