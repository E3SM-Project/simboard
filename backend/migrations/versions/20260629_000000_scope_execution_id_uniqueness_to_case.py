"""Scope simulation execution_id uniqueness to case.

Revision ID: 20260629_000000
Revises: 20260625_130000
Create Date: 2026-06-29 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260629_000000"
down_revision: Union[str, Sequence[str], None] = "20260625_130000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Scope execution identifier uniqueness to a case."""
    op.drop_index("ix_simulations_execution_id", table_name="simulations")
    op.create_index(
        "ix_simulations_execution_id",
        "simulations",
        ["execution_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_simulations_case_id_execution_id",
        "simulations",
        ["case_id", "execution_id"],
    )


def downgrade() -> None:
    """Downgrade intentionally unsupported."""
    raise RuntimeError(
        "Downgrade blocked: restoring global execution_id uniqueness would reject "
        "valid cross-case execution records. Restore from a database backup instead."
    )
