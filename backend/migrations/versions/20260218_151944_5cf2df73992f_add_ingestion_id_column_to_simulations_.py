"""Add ingestion_id column to simulations table

Revision ID: 5cf2df73992f
Revises: 6884b6060bed
Create Date: 2026-02-18 15:19:44.278145

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5cf2df73992f"
down_revision: Union[str, Sequence[str], None] = "6884b6060bed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Precondition: existing rows in simulations must be removed before running
    this migration.
    """
    op.add_column("simulations", sa.Column("ingestion_id", sa.UUID(), nullable=False))
    op.create_index(
        op.f("ix_simulations_ingestion_id"),
        "simulations",
        ["ingestion_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_simulations_ingestion_id_ingestions"),
        "simulations",
        "ingestions",
        ["ingestion_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_simulations_ingestion_id_ingestions"),
        "simulations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_simulations_ingestion_id"), table_name="simulations")
    op.drop_column("simulations", "ingestion_id")
