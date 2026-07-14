"""Add immutable execution discovery results.

Revision ID: 20260714_000000
Revises: 20260629_000000
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_000000"
down_revision: Union[str, Sequence[str], None] = "20260629_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create immutable discovery-result storage."""
    op.create_table(
        "execution_discovery_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_identity", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "accepted",
                "rejected_incomplete",
                "rejected_invalid",
                name="execution_discovery_outcome_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "machine_id",
            "case_identity",
            "execution_id",
            name="uq_execution_discovery_result_identity",
        ),
    )
    op.create_index(
        "ix_execution_discovery_results_lookup",
        "execution_discovery_results",
        ["machine_id", "case_identity"],
    )


def downgrade() -> None:
    """Drop immutable discovery-result storage."""
    op.drop_index(
        "ix_execution_discovery_results_lookup",
        table_name="execution_discovery_results",
    )
    op.drop_table("execution_discovery_results")
