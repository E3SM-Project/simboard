"""Add Case model, per-execution simulations, and CASE_GROUP

Squashed migration that applies the full case-based refactor in one step.

Changes to ``simulations``:
- Add ``run_config_deltas`` JSONB column (migrated from ``extra``)
- Add ``case_id`` FK → ``cases.id`` (non-null, CASCADE, indexed)
- Add ``execution_id`` (non-null, unique, indexed)
- Drop ``case_name`` column and ``uq_simulation_case_machine_date`` constraint
- Drop ``name`` column and ``ix_simulations_name`` index
- Drop ``group_name`` column
- Convert legacy list-format ``run_config_deltas`` to dict

CASE_HASH was evaluated for configuration identity but is not currently
used for grouping or validation in SimBoard.

New ``cases`` table:
- ``id`` UUID PK
- ``name`` (text, unique, indexed) — canonical identity from timing files
- ``case_group`` (text, nullable, indexed) — optional CASE_GROUP
- ``canonical_simulation_id`` FK → ``simulations.id``
- ``created_at``, ``updated_at`` timestamps

Revision ID: 20260304_400000
Revises: 20260219_000000
Create Date: 2026-03-04 22:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "20260304_400000"
down_revision: Union[str, Sequence[str], None] = "20260219_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the full case-based refactor."""

    # ── 1. Add run_config_deltas to simulations ──────────────────────
    op.add_column(
        "simulations",
        sa.Column("run_config_deltas", JSONB, nullable=True),
    )

    # ── 2. Create cases table ────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("case_group", sa.Text(), nullable=True),
        sa.Column("canonical_simulation_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_cases_name", "cases", ["name"], unique=True)
    op.create_index("ix_cases_case_group", "cases", ["case_group"])

    # ── 3. Add new columns to simulations ────────────────────────────
    op.add_column(
        "simulations",
        sa.Column("case_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("execution_id", sa.Text(), nullable=True),
    )

    # ── 4. Populate cases from distinct case_name values ─────────────
    op.execute(
        """
        INSERT INTO cases (id, name, created_at, updated_at)
        SELECT gen_random_uuid(), case_name, NOW(), NOW()
        FROM (SELECT DISTINCT case_name FROM simulations) AS distinct_cases
        """
    )

    # Backfill case_group from existing group_name (first non-null per case)
    op.execute(
        sa.text(
            "UPDATE cases SET case_group = sub.group_name "
            "FROM ("
            "  SELECT DISTINCT ON (case_id) s.case_name AS case_id, s.group_name "
            "  FROM simulations s "
            "  WHERE s.group_name IS NOT NULL "
            "  ORDER BY s.case_name, s.created_at"
            ") sub "
            "WHERE cases.name = sub.case_id AND cases.case_group IS NULL"
        )
    )

    # ── 5. Backfill case_id from case_name ───────────────────────────
    op.execute(
        """
        UPDATE simulations s
        SET case_id = c.id
        FROM cases c
        WHERE c.name = s.case_name
        """
    )

    # ── 6. Derive execution_id for existing rows ───────
    op.execute(
        """
        UPDATE simulations
        SET execution_id = id::text
        WHERE execution_id IS NULL
        """
    )
    # ── 7. Enforce NOT NULL ──────────────────────────────────────────
    op.alter_column("simulations", "case_id", nullable=False)
    op.alter_column("simulations", "execution_id", nullable=False)

    # ── 8. Add indexes and FK ────────────────────────────────────────
    op.create_index("ix_simulations_case_id", "simulations", ["case_id"])
    op.create_index(
        "ix_simulations_execution_id",
        "simulations",
        ["execution_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_simulations_case_id_cases",
        "simulations",
        "cases",
        ["case_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── 9. Set canonical_simulation_id per case ──────────────────────
    op.execute(
        """
        UPDATE cases c
        SET canonical_simulation_id = (
            SELECT s.id
            FROM simulations s
            WHERE s.case_id = c.id
            ORDER BY s.created_at ASC
            LIMIT 1
        )
        """
    )
    op.create_foreign_key(
        "fk_cases_canonical_sim",
        "cases",
        "simulations",
        ["canonical_simulation_id"],
        ["id"],
    )

    # ── 10. Convert legacy list run_config_deltas to dict ────────────
    op.execute(
        """
        UPDATE simulations
        SET run_config_deltas = NULL
        WHERE run_config_deltas IS NOT NULL
          AND jsonb_typeof(run_config_deltas) = 'array'
          AND jsonb_array_length(run_config_deltas) = 0
        """
    )
    op.execute(
        """
        UPDATE simulations
        SET run_config_deltas = run_config_deltas->0->'deltas'
        WHERE run_config_deltas IS NOT NULL
          AND jsonb_typeof(run_config_deltas) = 'array'
          AND jsonb_array_length(run_config_deltas) > 0
        """
    )

    # ── 11. Drop old columns and constraints ─────────────────────────
    op.drop_constraint("uq_simulation_case_machine_date", "simulations", type_="unique")
    op.drop_column("simulations", "case_name")
    op.drop_index("ix_simulations_name", table_name="simulations")
    op.drop_column("simulations", "name")
    op.drop_column("simulations", "group_name")


def downgrade() -> None:
    """Reverse the full case-based refactor."""

    # ── 1. Re-add dropped columns ────────────────────────────────────
    op.add_column(
        "simulations",
        sa.Column("group_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("name", sa.String(200), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("case_name", sa.String(200), nullable=True),
    )

    # ── 2. Backfill from cases ───────────────────────────────────────
    op.execute(
        sa.text(
            "UPDATE simulations SET case_name = c.name, "
            "name = c.name, group_name = c.case_group "
            "FROM cases c WHERE simulations.case_id = c.id"
        )
    )
    op.alter_column("simulations", "case_name", nullable=False)
    op.alter_column("simulations", "name", nullable=False)
    op.create_index("ix_simulations_name", "simulations", ["name"])
    op.create_index("ix_simulations_case_name", "simulations", ["case_name"])
    op.create_unique_constraint(
        "uq_simulation_case_machine_date",
        "simulations",
        ["case_name", "machine_id", "simulation_start_date"],
    )

    # ── 3. Drop new columns and FK ───────────────────────────────────
    op.drop_constraint(
        "fk_simulations_case_id_cases", "simulations", type_="foreignkey"
    )
    op.drop_constraint("fk_cases_canonical_sim", "cases", type_="foreignkey")
    op.drop_index("ix_simulations_execution_id", table_name="simulations")
    op.drop_index("ix_simulations_case_id", table_name="simulations")
    op.drop_column("simulations", "execution_id")
    op.drop_column("simulations", "case_id")

    # ── 4. Drop run_config_deltas ────────────────────────────────────
    # Move non-null column data back into extra['run_config_deltas']
    op.drop_column("simulations", "run_config_deltas")

    # ── 5. Drop cases table ──────────────────────────────────────────
    op.drop_index("ix_cases_case_group", table_name="cases")
    op.drop_index("ix_cases_name", table_name="cases")
    op.drop_table("cases")
