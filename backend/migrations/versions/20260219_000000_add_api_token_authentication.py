"""Add API token authentication

Revision ID: 20260219_000000
Revises: 5cf2df73992f
Create Date: 2026-02-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "20260219_000000"
down_revision: Union[str, Sequence[str], None] = "5cf2df73992f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add SERVICE_ACCOUNT to user_role enum
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'SERVICE_ACCOUNT'")

    # Add hpc_username column to simulations table
    op.add_column(
        "simulations",
        sa.Column("hpc_username", sa.String(length=200), nullable=True),
    )

    # Create api_tokens table
    op.create_table(
        "api_tokens",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_api_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_api_tokens_token_hash"),
        "api_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop api_tokens table
    op.drop_index(op.f("ix_api_tokens_token_hash"), table_name="api_tokens")
    op.drop_table("api_tokens")

    # Drop hpc_username column from simulations
    op.drop_column("simulations", "hpc_username")

    # Note: PostgreSQL does not support removing enum values.
    # The SERVICE_ACCOUNT enum value will remain after downgrade.
