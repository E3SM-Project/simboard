"""Normalize case identity to case name + machine + HPC username.

Revision ID: 20260624_120000
Revises: 20260611_090000
Create Date: 2026-06-24 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "20260624_120000"
down_revision: Union[str, Sequence[str], None] = "20260611_090000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNKNOWN_HPC_USERNAME = "__unknown__"


def upgrade() -> None:
    """Split legacy cases by normalized identity and enforce composite uniqueness."""
    op.add_column(
        "cases",
        sa.Column("machine_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column("hpc_username", sa.String(length=200), nullable=True),
    )
    op.create_foreign_key(
        "fk_cases_machine_id_machines",
        "cases",
        "machines",
        ["machine_id"],
        ["id"],
    )
    op.create_index("ix_cases_machine_id", "cases", ["machine_id"], unique=False)

    op.drop_index("ix_cases_name", table_name="cases")
    op.create_index("ix_cases_name", "cases", ["name"], unique=False)

    op.execute(
        sa.text(
            """
            UPDATE cases c
            SET
                machine_id = resolved.machine_id,
                hpc_username = resolved.hpc_username
            FROM (
                SELECT DISTINCT
                    s.case_id,
                    s.machine_id,
                    COALESCE(NULLIF(BTRIM(s.hpc_username), ''), :unknown_hpc_username)
                        AS hpc_username
                FROM simulations s
                JOIN (
                    SELECT s.case_id
                    FROM simulations s
                    GROUP BY s.case_id
                    HAVING COUNT(
                        DISTINCT ROW(
                            s.machine_id,
                            COALESCE(
                                NULLIF(BTRIM(s.hpc_username), ''),
                                :unknown_hpc_username
                            )
                        )
                    ) = 1
                ) AS single_identity
                    ON single_identity.case_id = s.case_id
            ) AS resolved
            WHERE c.id = resolved.case_id
            """
        ).bindparams(unknown_hpc_username=UNKNOWN_HPC_USERNAME)
    )

    op.execute(
        sa.text(
            """
            CREATE TEMP TABLE case_identity_split_map ON COMMIT DROP AS
            SELECT
                c.id AS old_case_id,
                gen_random_uuid() AS new_case_id,
                c.name,
                c.case_group,
                c.created_at,
                c.updated_at,
                split_identity.machine_id,
                split_identity.hpc_username
            FROM cases c
            JOIN (
                SELECT DISTINCT
                    s.case_id,
                    s.machine_id,
                    COALESCE(NULLIF(BTRIM(s.hpc_username), ''), :unknown_hpc_username)
                        AS hpc_username
                FROM simulations s
            ) AS split_identity
                ON split_identity.case_id = c.id
            WHERE c.id IN (
                SELECT s.case_id
                FROM simulations s
                GROUP BY s.case_id
                HAVING COUNT(
                    DISTINCT ROW(
                        s.machine_id,
                        COALESCE(NULLIF(BTRIM(s.hpc_username), ''), :unknown_hpc_username)
                    )
                ) > 1
            )
            """
        ).bindparams(unknown_hpc_username=UNKNOWN_HPC_USERNAME)
    )

    op.execute(
        """
        INSERT INTO cases (
            id,
            name,
            machine_id,
            hpc_username,
            case_group,
            created_at,
            updated_at
        )
        SELECT
            new_case_id,
            name,
            machine_id,
            hpc_username,
            case_group,
            created_at,
            updated_at
        FROM case_identity_split_map
        """
    )

    op.execute(
        sa.text(
            """
            UPDATE simulations s
            SET case_id = split_map.new_case_id
            FROM case_identity_split_map AS split_map
            WHERE s.case_id = split_map.old_case_id
              AND s.machine_id = split_map.machine_id
              AND COALESCE(NULLIF(BTRIM(s.hpc_username), ''), :unknown_hpc_username)
                    = split_map.hpc_username
            """
        ).bindparams(unknown_hpc_username=UNKNOWN_HPC_USERNAME)
    )

    op.execute(
        """
        DELETE FROM cases
        WHERE id IN (SELECT DISTINCT old_case_id FROM case_identity_split_map)
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM cases
                WHERE machine_id IS NULL OR hpc_username IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Case identity backfill failed; unresolved rows remain in cases.';
            END IF;
        END
        $$;
        """
    )

    op.alter_column("cases", "machine_id", nullable=False)
    op.alter_column("cases", "hpc_username", nullable=False)
    op.create_unique_constraint(
        "uq_cases_name_machine_id_hpc_username",
        "cases",
        ["name", "machine_id", "hpc_username"],
    )


def downgrade() -> None:
    """Case identity normalization is intentionally forward-only."""
    raise RuntimeError(
        "Downgrade not supported for normalized case identity migration."
    )
