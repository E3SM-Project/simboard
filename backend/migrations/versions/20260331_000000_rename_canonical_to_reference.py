"""Rename canonical simulation terminology to reference.

Revision ID: 20260331_000000
Revises: 20260323_000000
Create Date: 2026-03-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_000000"
down_revision: Union[str, Sequence[str], None] = "20260323_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_run_config_delta_key(source_key: str, target_key: str) -> None:
    op.execute(
        f"""
        UPDATE simulations
        SET run_config_deltas = CASE
            WHEN jsonb_typeof(run_config_deltas) = 'object' THEN (
                SELECT jsonb_object_agg(
                    delta.key,
                    CASE
                        WHEN jsonb_typeof(delta.value) = 'object' AND delta.value ? '{source_key}'
                        THEN jsonb_build_object('{target_key}', delta.value -> '{source_key}')
                             || (delta.value - '{source_key}')
                        ELSE delta.value
                    END
                )
                FROM jsonb_each(run_config_deltas) AS delta(key, value)
            )
            ELSE run_config_deltas
        END
        WHERE run_config_deltas IS NOT NULL;
        """
    )


def upgrade() -> None:
    """Rename persisted canonical fields and delta payloads to reference."""
    op.drop_constraint("fk_cases_canonical_sim", "cases", type_="foreignkey")
    op.alter_column(
        "cases",
        "canonical_simulation_id",
        new_column_name="reference_simulation_id",
    )
    op.create_foreign_key(
        "fk_cases_reference_sim",
        "cases",
        "simulations",
        ["reference_simulation_id"],
        ["id"],
    )
    _rename_run_config_delta_key("canonical", "reference")


def downgrade() -> None:
    """Restore canonical terminology for persisted case and delta fields."""
    _rename_run_config_delta_key("reference", "canonical")
    op.drop_constraint("fk_cases_reference_sim", "cases", type_="foreignkey")
    op.alter_column(
        "cases",
        "reference_simulation_id",
        new_column_name="canonical_simulation_id",
    )
    op.create_foreign_key(
        "fk_cases_canonical_sim",
        "cases",
        "simulations",
        ["canonical_simulation_id"],
        ["id"],
    )
