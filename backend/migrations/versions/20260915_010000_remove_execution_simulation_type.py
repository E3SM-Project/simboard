"""Remove legacy execution simulation type.

Revision ID: 20260915_010000
Revises: 20260915_000000
Create Date: 2026-09-15 01:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_010000"
down_revision: Union[str, Sequence[str], None] = "20260915_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("executions", "simulation_type")


def downgrade() -> None:
    op.add_column(
        "executions",
        sa.Column(
            "simulation_type",
            sa.Enum(
                "unknown",
                "production",
                "experimental",
                "test",
                name="simulation_type_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="unknown",
        ),
    )
