"""Add scheduled job registrations and run records.

Revision ID: 20261112_010000
Revises: 20261112_000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261112_010000"
down_revision = "20261112_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_mode", sa.String(20), nullable=False),
        sa.Column("service_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_silence_minutes", sa.Integer(), nullable=False),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"]),
        sa.ForeignKeyConstraint(["service_account_id"], ["users.id"]),
    )
    op.create_index("ix_scheduled_jobs_machine_id", "scheduled_jobs", ["machine_id"])
    op.create_table(
        "scheduled_job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finish_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.String(11), nullable=True),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column("failure_status_code", sa.Integer(), nullable=True),
        sa.Column("failure_transient", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_scheduled_job_runs_job_reported",
        "scheduled_job_runs",
        ["job_id", "reported_at"],
    )


def downgrade() -> None:
    op.drop_table("scheduled_job_runs")
    op.drop_table("scheduled_jobs")
