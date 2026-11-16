"""Add failed case uploads to scheduled job run records.

Revision ID: 20261112_020000
Revises: 20261112_010000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261112_020000"
down_revision = "20261112_010000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_job_runs",
        sa.Column(
            "upload_failures", postgresql.JSONB(none_as_null=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_job_runs", "upload_failures")
