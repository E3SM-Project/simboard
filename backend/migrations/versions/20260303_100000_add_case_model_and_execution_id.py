"""Add Case model, case_id, execution_id to Simulation

Revision ID: 20260303_100000
Revises: 20260303_000000
Create Date: 2026-03-03 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "20260303_100000"
down_revision: Union[str, Sequence[str], None] = "20260303_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cases table and migrate simulations to case-based model."""

    # 1. Create cases table (without canonical_simulation_id FK first)
    op.create_table(
        "cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("canonical_simulation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cases_name", "cases", ["name"], unique=True)

    # 2. Add case_id (nullable initially) and execution_id to simulations
    op.add_column(
        "simulations",
        sa.Column("case_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("execution_id", sa.Text(), nullable=True),
    )

    # 3. Populate cases from distinct case_name values
    op.execute(
        """
        INSERT INTO cases (id, name, created_at, updated_at)
        SELECT gen_random_uuid(), case_name, NOW(), NOW()
        FROM (SELECT DISTINCT case_name FROM simulations) AS distinct_cases
        """
    )

    # 4. Backfill case_id from case_name
    op.execute(
        """
        UPDATE simulations s
        SET case_id = c.id
        FROM cases c
        WHERE c.name = s.case_name
        """
    )

    # 5. Derive execution_id from id (fallback for existing rows)
    #    Existing rows don't have archive directory names, so use
    #    a text representation of their UUID as execution_id.
    op.execute(
        """
        UPDATE simulations
        SET execution_id = id::text
        WHERE execution_id IS NULL
        """
    )

    # 6. Make case_id and execution_id non-nullable
    op.alter_column("simulations", "case_id", nullable=False)
    op.alter_column("simulations", "execution_id", nullable=False)

    # 7. Add indexes and constraints
    op.create_index("ix_simulations_case_id", "simulations", ["case_id"])
    op.create_index(
        "ix_simulations_execution_id", "simulations", ["execution_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_simulations_case_id_cases",
        "simulations", "cases",
        ["case_id"], ["id"],
    )

    # 8. Set canonical_simulation_id for each case (earliest simulation)
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

    # 9. Add FK from cases.canonical_simulation_id -> simulations.id
    op.create_foreign_key(
        "fk_cases_canonical_sim",
        "cases", "simulations",
        ["canonical_simulation_id"], ["id"],
    )

    # 10. Convert run_config_deltas from list to dict if legacy data exists
    #     Legacy format was a list; new format is a single dict or null.
    #     If the column contains a JSON array, unwrap the first element's
    #     "deltas" key.  Otherwise leave as-is.
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

    # 11. Drop old case_name column and its unique constraint
    op.drop_constraint(
        "uq_simulation_case_machine_date", "simulations", type_="unique"
    )
    op.drop_column("simulations", "case_name")


def downgrade() -> None:
    """Reverse the case-based migration."""

    # Re-add case_name column
    op.add_column(
        "simulations",
        sa.Column("case_name", sa.String(200), nullable=True),
    )

    # Backfill case_name from cases table
    op.execute(
        """
        UPDATE simulations s
        SET case_name = c.name
        FROM cases c
        WHERE c.id = s.case_id
        """
    )
    op.alter_column("simulations", "case_name", nullable=False)
    op.create_index("ix_simulations_case_name", "simulations", ["case_name"])

    # Re-create the old unique constraint
    op.create_unique_constraint(
        "uq_simulation_case_machine_date",
        "simulations",
        ["case_name", "machine_id", "simulation_start_date"],
    )

    # Drop FK and indexes for new columns
    op.drop_constraint(
        "fk_simulations_case_id_cases", "simulations", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_cases_canonical_sim", "cases", type_="foreignkey"
    )
    op.drop_index("ix_simulations_execution_id", table_name="simulations")
    op.drop_index("ix_simulations_case_id", table_name="simulations")

    # Drop new columns
    op.drop_column("simulations", "execution_id")
    op.drop_column("simulations", "case_id")

    # Drop cases table
    op.drop_index("ix_cases_name", table_name="cases")
    op.drop_table("cases")
