"""Remove persisted reference and delta fields from cases and simulations.

Revision ID: 20260604_120000
Revises: e1a37fccb0f7
Create Date: 2026-06-04 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260604_120000"
down_revision: Union[str, Sequence[str], None] = "e1a37fccb0f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop obsolete reference-tracking columns."""
    op.drop_constraint("fk_cases_reference_sim", "cases", type_="foreignkey")
    op.drop_column("cases", "reference_simulation_id")
    op.drop_column("simulations", "run_config_deltas")


def downgrade() -> None:
    """Restore removed reference-tracking columns."""
    op.add_column(
        "simulations",
        sa.Column("run_config_deltas", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column("reference_simulation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cases_reference_sim",
        "cases",
        "simulations",
        ["reference_simulation_id"],
        ["id"],
    )
