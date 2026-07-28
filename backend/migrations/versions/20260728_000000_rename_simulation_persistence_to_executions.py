"""Rename simulation entity persistence to execution terminology.

Revision ID: 20260728_000000
Revises: 20260722_000000
Create Date: 2026-07-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260728_000000"
down_revision: Union[str, Sequence[str], None] = "20260722_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_constraint(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(
        f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'
    )


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    """Rename current persistence objects without rewriting stored rows."""
    op.rename_table("simulations", "executions")
    op.alter_column(
        "artifacts",
        "simulation_id",
        new_column_name="execution_id",
    )
    op.alter_column(
        "external_links",
        "simulation_id",
        new_column_name="execution_id",
    )

    constraint_renames = (
        ("executions", "pk_simulations", "pk_executions"),
        (
            "executions",
            "uq_simulations_case_id_execution_id",
            "uq_executions_case_id_execution_id",
        ),
        (
            "executions",
            "ck_simulations_compute_type",
            "ck_executions_compute_type",
        ),
        (
            "executions",
            "fk_simulations_case_id_cases",
            "fk_executions_case_id_cases",
        ),
        (
            "executions",
            "fk_simulations_created_by_users",
            "fk_executions_created_by_users",
        ),
        (
            "executions",
            "fk_simulations_last_updated_by_users",
            "fk_executions_last_updated_by_users",
        ),
        (
            "executions",
            "fk_simulations_ingestion_id_ingestions",
            "fk_executions_ingestion_id_ingestions",
        ),
        (
            "artifacts",
            "fk_artifacts_simulation_id_simulations",
            "fk_artifacts_execution_id_executions",
        ),
        (
            "external_links",
            "fk_external_links_simulation_id_simulations",
            "fk_external_links_execution_id_executions",
        ),
    )
    for table_name, old_name, new_name in constraint_renames:
        _rename_constraint(table_name, old_name, new_name)

    index_renames = (
        ("ix_simulations_case_id", "ix_executions_case_id"),
        ("ix_simulations_execution_id", "ix_executions_execution_id"),
        ("ix_simulations_status", "ix_executions_status"),
        ("ix_simulations_git_commit_hash", "ix_executions_git_commit_hash"),
        ("ix_simulations_created_by", "ix_executions_created_by"),
        ("ix_simulations_last_updated_by", "ix_executions_last_updated_by"),
        ("ix_simulations_ingestion_id", "ix_executions_ingestion_id"),
        ("ix_artifacts_simulation_id", "ix_artifacts_execution_id"),
    )
    for old_name, new_name in index_renames:
        _rename_index(old_name, new_name)


def downgrade() -> None:
    """Restore simulation-oriented persistence names."""
    index_renames = (
        ("ix_executions_case_id", "ix_simulations_case_id"),
        ("ix_executions_execution_id", "ix_simulations_execution_id"),
        ("ix_executions_status", "ix_simulations_status"),
        ("ix_executions_git_commit_hash", "ix_simulations_git_commit_hash"),
        ("ix_executions_created_by", "ix_simulations_created_by"),
        ("ix_executions_last_updated_by", "ix_simulations_last_updated_by"),
        ("ix_executions_ingestion_id", "ix_simulations_ingestion_id"),
        ("ix_artifacts_execution_id", "ix_artifacts_simulation_id"),
    )
    for old_name, new_name in index_renames:
        _rename_index(old_name, new_name)

    constraint_renames = (
        ("executions", "pk_executions", "pk_simulations"),
        (
            "executions",
            "uq_executions_case_id_execution_id",
            "uq_simulations_case_id_execution_id",
        ),
        (
            "executions",
            "ck_executions_compute_type",
            "ck_simulations_compute_type",
        ),
        (
            "executions",
            "fk_executions_case_id_cases",
            "fk_simulations_case_id_cases",
        ),
        (
            "executions",
            "fk_executions_created_by_users",
            "fk_simulations_created_by_users",
        ),
        (
            "executions",
            "fk_executions_last_updated_by_users",
            "fk_simulations_last_updated_by_users",
        ),
        (
            "executions",
            "fk_executions_ingestion_id_ingestions",
            "fk_simulations_ingestion_id_ingestions",
        ),
        (
            "artifacts",
            "fk_artifacts_execution_id_executions",
            "fk_artifacts_simulation_id_simulations",
        ),
        (
            "external_links",
            "fk_external_links_execution_id_executions",
            "fk_external_links_simulation_id_simulations",
        ),
    )
    for table_name, old_name, new_name in constraint_renames:
        _rename_constraint(table_name, old_name, new_name)

    op.alter_column(
        "external_links",
        "execution_id",
        new_column_name="simulation_id",
    )
    op.alter_column(
        "artifacts",
        "execution_id",
        new_column_name="simulation_id",
    )
    op.rename_table("executions", "simulations")
