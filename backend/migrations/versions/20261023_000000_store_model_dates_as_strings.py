"""Store model dates as strings to preserve astronomical year zero.

Revision ID: 20261023_000000
Revises: 20261006_000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_000000"
down_revision = "20261006_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do not silently truncate dates outside the application's supported range.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM executions
                WHERE simulation_start_date < DATE '0001-01-01'
                   OR simulation_start_date > DATE '9999-12-31'
                   OR simulation_end_date < DATE '0001-01-01'
                   OR simulation_end_date > DATE '9999-12-31'
            ) THEN
                RAISE EXCEPTION 'Model dates outside years 0001-9999 require explicit conversion';
            END IF;
        END $$;
    """)
    for column in ("simulation_start_date", "simulation_end_date"):
        op.alter_column(
            "executions",
            column,
            existing_type=sa.Date(),
            type_=sa.String(10),
            postgresql_using=f"to_char({column}, 'YYYY-MM-DD')",
        )


def downgrade() -> None:
    # PostgreSQL DATE has no literal year zero. Never shift or discard it.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM executions
                WHERE simulation_start_date LIKE '0000-%'
                   OR simulation_end_date LIKE '0000-%'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade model dates while year-zero records exist';
            END IF;
        END $$;
    """)
    for column in ("simulation_start_date", "simulation_end_date"):
        op.alter_column(
            "executions",
            column,
            existing_type=sa.String(10),
            type_=sa.Date(),
            postgresql_using=f"{column}::date",
        )
