"""Add user-managed case simulation type.

Revision ID: 20260915_000000
Revises: 20260811_000000
Create Date: 2026-09-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_000000"
down_revision: Union[str, Sequence[str], None] = "20260811_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases", sa.Column("simulation_type", sa.String(length=20), nullable=True)
    )
    op.create_check_constraint(
        "case_simulation_type",
        "cases",
        "simulation_type IS NULL OR simulation_type IN ('production', 'development')",
    )


def downgrade() -> None:
    op.drop_constraint("case_simulation_type", "cases", type_="check")
    op.drop_column("cases", "simulation_type")
