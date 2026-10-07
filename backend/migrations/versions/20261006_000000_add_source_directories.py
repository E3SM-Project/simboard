"""Add original performance source directories.

Revision ID: 20261006_000000
Revises: 20260915_010000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261006_000000"
down_revision: Union[str, Sequence[str], None] = "20260915_010000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_directories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "(case_id IS NOT NULL) <> (execution_id IS NOT NULL)",
            name="exactly_one_owner",
        ),
        sa.CheckConstraint(
            "kind IN ('staging', 'archive')", name="source_directory_kind"
        ),
    )
    for owner in ("case", "execution"):
        op.create_index(
            f"uq_source_directories_{owner}",
            "source_directories",
            [f"{owner}_id", "kind", "path"],
            unique=True,
            postgresql_where=sa.text(f"{owner}_id IS NOT NULL"),
        )


def downgrade() -> None:
    op.drop_table("source_directories")
