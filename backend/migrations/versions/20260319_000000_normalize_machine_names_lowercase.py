"""Normalize machine names to lowercase and enforce case-insensitive uniqueness.

Revision ID: 20260319_000000
Revises: 20260304_400000
Create Date: 2026-03-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260319_000000"
down_revision: Union[str, Sequence[str], None] = "20260304_400000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Normalize machine names and enforce case-insensitive uniqueness."""
    connection = op.get_bind()

    duplicate_names = connection.execute(
        sa.text(
            """
            SELECT lower(name) AS normalized_name
            FROM machines
            GROUP BY lower(name)
            HAVING COUNT(*) > 1
            ORDER BY lower(name)
            """
        )
    ).scalars()
    duplicate_names = list(duplicate_names)

    if duplicate_names:
        conflicts = ", ".join(duplicate_names)
        raise RuntimeError(
            "Cannot normalize machine names because case-insensitive duplicates "
            f"already exist: {conflicts}"
        )

    op.execute(
        sa.text("UPDATE machines SET name = lower(name) WHERE name <> lower(name)")
    )
    op.create_check_constraint(
        "ck_machines_name_lowercase",
        "machines",
        "name = lower(name)",
    )
    op.drop_index(op.f("ix_machines_name"), table_name="machines")
    op.create_index(
        "uq_machines_name_lower",
        "machines",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    """Restore the original case-sensitive unique index."""
    op.drop_index("uq_machines_name_lower", table_name="machines")
    op.drop_constraint("ck_machines_name_lowercase", "machines", type_="check")
    op.create_index(op.f("ix_machines_name"), "machines", ["name"], unique=True)
