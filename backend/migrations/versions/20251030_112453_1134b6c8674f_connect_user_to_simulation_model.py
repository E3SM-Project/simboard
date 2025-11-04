"""Connect user to simulation model

Revision ID: 1134b6c8674f
Revises: 0ce2ab7d6d15
Create Date: 2025-10-30 11:24:53.850754
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1134b6c8674f"
down_revision: Union[str, Sequence[str], None] = "0ce2ab7d6d15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Convert string -> UUID with explicit cast
    op.alter_column(
        "simulations",
        "created_by",
        existing_type=sa.VARCHAR(length=100),
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="created_by::uuid",
        nullable=False,
    )
    op.alter_column(
        "simulations",
        "last_updated_by",
        existing_type=sa.VARCHAR(length=100),
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="last_updated_by::uuid",
        nullable=False,
    )

    # Add indexes
    op.create_index(
        op.f("ix_simulations_created_by"), "simulations", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_simulations_last_updated_by"),
        "simulations",
        ["last_updated_by"],
        unique=False,
    )

    # Add foreign keys
    op.create_foreign_key(
        op.f("fk_simulations_created_by_users"),
        "simulations",
        "users",
        ["created_by"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_simulations_last_updated_by_users"),
        "simulations",
        "users",
        ["last_updated_by"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_simulations_created_by_users"), "simulations", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_simulations_last_updated_by_users"), "simulations", type_="foreignkey"
    )
    op.drop_index(op.f("ix_simulations_last_updated_by"), table_name="simulations")
    op.drop_index(op.f("ix_simulations_created_by"), table_name="simulations")

    # Revert UUID -> VARCHAR (string)
    op.alter_column(
        "simulations",
        "last_updated_by",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.VARCHAR(length=100),
        postgresql_using="last_updated_by::text",
        nullable=True,
    )
    op.alter_column(
        "simulations",
        "created_by",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.VARCHAR(length=100),
        postgresql_using="created_by::text",
        nullable=True,
    )
