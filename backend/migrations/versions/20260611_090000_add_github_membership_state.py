"""Persist GitHub org membership state used for edit authorization.

Revision ID: 20260611_090000
Revises: 20260604_120000
Create Date: 2026-06-11 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260611_090000"
down_revision: Union[str, Sequence[str], None] = "20260604_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist edit-authorization inputs on users."""
    op.add_column(
        "users",
        sa.Column(
            "has_verified_e3sm_membership",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("github_org_membership_checked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    """Drop persisted edit-authorization fields from users."""
    op.drop_column("users", "github_org_membership_checked_at")
    op.drop_column("users", "has_verified_e3sm_membership")
