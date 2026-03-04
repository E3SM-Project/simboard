"""Move case_hash from cases to simulations

CASE_HASH changes between executions of the same case, so it belongs
on the Simulation (execution metadata), not the Case (experiment identity).

This migration:
1. Adds ``case_hash`` (NOT NULL, indexed) to ``simulations``, backfilling
   from the parent Case.
2. Drops ``case_hash`` (and its unique constraint/index) from ``cases``.

Revision ID: 20260304_300000
Revises: 20260304_200000
Create Date: 2026-03-04 22:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260304_300000"
down_revision: Union[str, Sequence[str], None] = "20260304_200000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Move ``case_hash`` from ``cases`` to ``simulations``."""
    # 1. Add nullable case_hash to simulations.
    op.add_column(
        "simulations",
        sa.Column("case_hash", sa.Text(), nullable=True),
    )

    # 2. Backfill from parent case.
    op.execute(
        sa.text(
            "UPDATE simulations SET case_hash = c.case_hash "
            "FROM cases c WHERE simulations.case_id = c.id"
        )
    )

    # 3. Set remaining NULLs to empty string (safety net).
    op.execute(sa.text("UPDATE simulations SET case_hash = '' WHERE case_hash IS NULL"))

    # 4. Enforce NOT NULL.
    op.alter_column("simulations", "case_hash", nullable=False)

    # 5. Add index on simulation.case_hash.
    op.create_index("ix_simulations_case_hash", "simulations", ["case_hash"])

    # 6. Drop case_hash from cases.
    op.drop_index("ix_cases_case_hash", table_name="cases")
    op.drop_constraint("uq_cases_case_hash", "cases", type_="unique")
    op.drop_column("cases", "case_hash")


def downgrade() -> None:
    """Restore ``case_hash`` on ``cases``, drop from ``simulations``."""
    # 1. Re-add case_hash to cases (nullable initially).
    op.add_column(
        "cases",
        sa.Column("case_hash", sa.Text(), nullable=True),
    )

    # 2. Backfill from the first simulation per case.
    op.execute(
        sa.text(
            "UPDATE cases SET case_hash = sub.case_hash "
            "FROM ("
            "  SELECT DISTINCT ON (case_id) case_id, case_hash "
            "  FROM simulations ORDER BY case_id, created_at"
            ") sub WHERE cases.id = sub.case_id"
        )
    )

    # 3. Fill any remaining NULLs with SHA-256 of name.
    op.execute(
        sa.text(
            "UPDATE cases SET case_hash = encode("
            "sha256(name::bytea), 'hex') WHERE case_hash IS NULL"
        )
    )

    # 4. Enforce NOT NULL + UNIQUE.
    op.alter_column("cases", "case_hash", nullable=False)
    op.create_unique_constraint("uq_cases_case_hash", "cases", ["case_hash"])
    op.create_index("ix_cases_case_hash", "cases", ["case_hash"], unique=True)

    # 5. Drop case_hash from simulations.
    op.drop_index("ix_simulations_case_hash", table_name="simulations")
    op.drop_column("simulations", "case_hash")
