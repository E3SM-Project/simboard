"""Normalize case_group: add to cases, drop group_name from simulations

Move CASE_GROUP from simulation-level ``group_name`` to case-level
``case_group``.  The existing ``group_name`` values are migrated to
the parent Case before the column is dropped.

Revision ID: 20260304_200000
Revises: 20260304_100000
Create Date: 2026-03-04 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260304_200000"
down_revision: Union[str, Sequence[str], None] = "20260304_100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``case_group`` to ``cases`` and drop ``group_name`` from ``simulations``."""
    # 1. Add nullable case_group column with index.
    op.add_column(
        "cases",
        sa.Column("case_group", sa.Text(), nullable=True),
    )
    op.create_index("ix_cases_case_group", "cases", ["case_group"])

    # 2. Backfill: copy the first non-null group_name per case.
    op.execute(
        sa.text(
            "UPDATE cases SET case_group = sub.group_name "
            "FROM ("
            "  SELECT DISTINCT ON (case_id) case_id, group_name "
            "  FROM simulations "
            "  WHERE group_name IS NOT NULL "
            "  ORDER BY case_id, created_at"
            ") sub "
            "WHERE cases.id = sub.case_id AND cases.case_group IS NULL"
        )
    )

    # 3. Drop group_name from simulations.
    op.drop_column("simulations", "group_name")


def downgrade() -> None:
    """Restore ``group_name`` on ``simulations`` and drop ``case_group`` from ``cases``."""
    # 1. Re-add group_name to simulations.
    op.add_column(
        "simulations",
        sa.Column("group_name", sa.Text(), nullable=True),
    )

    # 2. Backfill from parent case.
    op.execute(
        sa.text(
            "UPDATE simulations SET group_name = cases.case_group "
            "FROM cases "
            "WHERE simulations.case_id = cases.id "
            "AND cases.case_group IS NOT NULL"
        )
    )

    # 3. Drop case_group from cases.
    op.drop_index("ix_cases_case_group", table_name="cases")
    op.drop_column("cases", "case_group")
