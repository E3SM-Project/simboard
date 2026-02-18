"""Make ingestion status and source type enums

Revision ID: 6884b6060bed
Revises: 83737ddf5074
Create Date: 2026-02-18 12:27:55.580476

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6884b6060bed"
down_revision: Union[str, Sequence[str], None] = "83737ddf5074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "ingestions",
        "source_type",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum(
            "hpc_path",
            "hpc_upload",
            "browser_upload",
            name="ingestion_source_type_enum",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "ingestions",
        "status",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.Enum(
            "success",
            "partial",
            "failed",
            name="ingestion_status_enum",
            native_enum=False,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "ingestions",
        "status",
        existing_type=sa.Enum(
            "success",
            "partial",
            "failed",
            name="ingestion_status_enum",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "ingestions",
        "source_type",
        existing_type=sa.Enum(
            "hpc_path",
            "hpc_upload",
            "browser_upload",
            name="ingestion_source_type_enum",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )
