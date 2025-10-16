"""Seed machines table

Revision ID: d78e4ce0ddc7
Revises: 6bf905412036
Create Date: 2025-10-13 11:08:32.816288

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d78e4ce0ddc7"
down_revision: Union[str, Sequence[str], None] = "6bf905412036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    md = sa.MetaData()
    machines = sa.Table(
        "machines",
        md,
        # Adjust these to match your actual columns/types
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("site", sa.String(200), nullable=False),
        sa.Column("architecture", sa.String(100), nullable=False),
        sa.Column("scheduler", sa.String(100), nullable=False),
        sa.Column("gpu", sa.Boolean, nullable=False),
        sa.Column("notes", sa.Text),
        # Include these if your TimestampMixin columns are NOT NULL
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Current (2025) E3SM platforms & dedicated machines.
    seed_rows = [
        {
            "id": uuid.uuid4(),
            "name": "perlmutter",
            "site": "NERSC",
            "architecture": "AMD EPYC + NVIDIA A100",
            "scheduler": "slurm",
            "gpu": True,
            "notes": "Primary externally supported E3SM platform.",
        },
        {
            "id": uuid.uuid4(),
            "name": "frontier",
            "site": "OLCF",
            "architecture": "HPE Cray EX; AMD EPYC + AMD MI250X",
            "scheduler": "slurm",
            "gpu": True,
            "notes": "Leadership system at OLCF.",
        },
        {
            "id": uuid.uuid4(),
            "name": "polaris",
            "site": "ALCF",
            "architecture": "HPE Apollo; AMD EPYC + NVIDIA A100",
            "scheduler": "pbs",
            "gpu": True,
            "notes": "Leadership system at ALCF.",
        },
        {
            "id": uuid.uuid4(),
            "name": "aurora",
            "site": "ALCF",
            "architecture": "HPE Cray EX; Intel Xeon Max + Intel GPU Max",
            "scheduler": "pbs",
            "gpu": True,
            "notes": "Exascale system at ALCF.",
        },
        {
            "id": uuid.uuid4(),
            "name": "compy",
            "site": "PNNL",
            "architecture": "x86_64 CPU cluster",
            "scheduler": "slurm",
            "gpu": False,
            "notes": "E3SM-dedicated machine at PNNL.",
        },
        {
            "id": uuid.uuid4(),
            "name": "chrysalis",
            "site": "ANL (LCRC)",
            "architecture": "x86_64 CPU cluster",
            "scheduler": "slurm",
            "gpu": False,
            "notes": "E3SM-dedicated machine at ANL LCRC.",
        },
        {
            "id": uuid.uuid4(),
            "name": "anvil",
            "site": "ANL",
            "architecture": "x86_64 CPU cluster",
            "scheduler": "slurm",
            "gpu": False,
            "notes": "E3SM-dedicated machine at ANL (historical/limited availability).",
        },
        {
            "id": uuid.uuid4(),
            "name": "andes",
            "site": "OLCF",
            "architecture": "x86_64 CPU cluster (some GPU nodes)",
            "scheduler": "slurm",
            "gpu": False,
            "notes": "OLCF analysis/PP platform for Frontier output.",
        },
    ]

    op.bulk_insert(machines, seed_rows)


def downgrade() -> None:
    md = sa.MetaData()
    machines = sa.Table(
        "machines",
        md,
        sa.Column("name", sa.String(200)),
    )
    names = [
        "perlmutter",
        "frontier",
        "polaris",
        "aurora",
        "compy",
        "chrysalis",
        "anvil",
        "andes",
    ]
    op.execute(sa.delete(machines).where(machines.c.name.in_(names)))
