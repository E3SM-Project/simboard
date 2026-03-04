"""Add case_hash column to cases table

CASE_HASH (from env_case.xml) is now the mandatory identity for
Case grouping.  This column is NOT NULL and UNIQUE.

Existing rows are backfilled with a deterministic SHA-256 hash
derived from their ``name`` so the migration can complete.  Real
CASE_HASH values will be populated during subsequent ingestion.

Revision ID: 20260304_100000
Revises: 20260304_000000
Create Date: 2026-03-04 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260304_100000"
down_revision: Union[str, Sequence[str], None] = "20260304_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``case_hash`` to ``cases`` as NOT NULL + UNIQUE."""
    # 1. Add nullable column first.
    op.add_column(
        "cases",
        sa.Column("case_hash", sa.Text(), nullable=True),
    )

    # 2. Backfill: use SHA-256 of name as a temporary placeholder for
    #    existing rows.  Real CASE_HASH values from env_case.xml will
    #    replace these during subsequent ingestion.
    op.execute(
        sa.text(
            "UPDATE cases SET case_hash = encode("
            "sha256(name::bytea), 'hex') WHERE case_hash IS NULL"
        )
    )

    # 3. Enforce NOT NULL.
    op.alter_column("cases", "case_hash", nullable=False)

    # 4. Add unique constraint and index.
    op.create_unique_constraint("uq_cases_case_hash", "cases", ["case_hash"])
    op.create_index("ix_cases_case_hash", "cases", ["case_hash"], unique=True)


def downgrade() -> None:
    """Remove ``case_hash`` column from ``cases``."""
    op.drop_index("ix_cases_case_hash", table_name="cases")
    op.drop_constraint("uq_cases_case_hash", "cases", type_="unique")
    op.drop_column("cases", "case_hash")
