"""Update git fields on Simulation for clarity

Revision ID: 8e8b52805f00
Revises: d78e4ce0ddc7
Create Date: 2025-10-14 12:04:10.639899

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e8b52805f00"
down_revision: Union[str, Sequence[str], None] = "d78e4ce0ddc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Rename git-related fields on simulations table."""
    op.alter_column(
        "simulations", "external_repo_url", new_column_name="git_repository_url"
    )
    op.alter_column("simulations", "branch", new_column_name="git_branch")
    op.alter_column("simulations", "version_tag", new_column_name="git_tag")
    op.alter_column("simulations", "git_hash", new_column_name="git_commit_hash")

    op.drop_index(op.f("ix_simulations_git_hash"), table_name="simulations")
    op.drop_constraint(
        op.f("uq_simulation_name_version"), "simulations", type_="unique"
    )

    op.create_index(
        op.f("ix_simulations_git_commit_hash"),
        "simulations",
        ["git_commit_hash"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_simulation_name_tag", "simulations", ["name", "git_tag"]
    )


def downgrade() -> None:
    """Downgrade schema: Rename git fields back to original names."""
    op.drop_index(op.f("ix_simulations_git_commit_hash"), table_name="simulations")
    op.drop_constraint("uq_simulation_name_tag", "simulations", type_="unique")

    op.create_index(
        op.f("ix_simulations_git_hash"), "simulations", ["git_hash"], unique=False
    )
    op.create_unique_constraint(
        op.f("uq_simulation_name_version"),
        "simulations",
        ["name", "version_tag"],
        postgresql_nulls_not_distinct=False,
    )

    op.alter_column(
        "simulations", "git_repository_url", new_column_name="external_repo_url"
    )
    op.alter_column("simulations", "git_branch", new_column_name="branch")
    op.alter_column("simulations", "git_tag", new_column_name="version_tag")
    op.alter_column("simulations", "git_commit_hash", new_column_name="git_hash")
