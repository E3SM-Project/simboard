"""Seed status lookup table

Revision ID: 6bf905412036
Revises: 7fea50e608c8
Create Date: 2025-10-13 11:07:59.351019

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bf905412036"
down_revision: Union[str, Sequence[str], None] = "7fea50e608c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        sa.text(
            """
            INSERT INTO status_lookup (code, label) VALUES
              ('created','Created'),
              ('queued','Queued'),
              ('running','Running'),
              ('failed','Failed'),
              ('completed','Completed')
            ON CONFLICT (code) DO NOTHING;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "DELETE FROM status_lookup WHERE code IN ('created','queued','running','failed','completed');"
        )
    )
