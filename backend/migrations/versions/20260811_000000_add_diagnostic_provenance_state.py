"""Add successful diagnostics scanner provenance state.

Revision ID: 20260811_000000
Revises: 20260728_010000
Create Date: 2026-08-11 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_000000"
down_revision: Union[str, Sequence[str], None] = "20260728_010000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_provenance_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_name", sa.String(length=200), nullable=False),
        sa.Column("archive_relative_case_path", sa.Text(), nullable=False),
        sa.Column("settings_filename", sa.String(length=255), nullable=False),
        sa.Column("provenance_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("linked_url", sa.String(length=1000), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["external_links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", name="uq_diagnostic_provenance_states_link_id"),
        sa.UniqueConstraint(
            "machine_name",
            "archive_relative_case_path",
            name="uq_diagnostic_provenance_states_machine_path",
        ),
    )


def downgrade() -> None:
    op.drop_table("diagnostic_provenance_states")
