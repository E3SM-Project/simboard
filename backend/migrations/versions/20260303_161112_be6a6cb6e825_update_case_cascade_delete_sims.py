"""Update case cascade delete sims

Revision ID: be6a6cb6e825
Revises: 20260303_100000
Create Date: 2026-03-03 16:11:12.435888

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be6a6cb6e825"
down_revision: Union[str, Sequence[str], None] = "20260303_100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "cases",
        "id",
        existing_type=sa.UUID(),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_constraint(
        "fk_simulations_case_id_cases", "simulations", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_simulations_case_id_cases"),
        "simulations",
        "cases",
        ["case_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_simulations_case_id_cases"), "simulations", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_simulations_case_id_cases",
        "simulations",
        "cases",
        ["case_id"],
        ["id"],
    )
    op.alter_column(
        "cases",
        "id",
        existing_type=sa.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
