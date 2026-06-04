"""Allow external links to belong to either simulations or cases.

Revision ID: 20260604_130000
Revises: 20260604_120000
Create Date: 2026-06-04 13:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260604_130000"
down_revision: Union[str, Sequence[str], None] = "20260604_120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add case ownership support for external links."""
    op.add_column(
        "external_links",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_external_links_case_id_cases"),
        "external_links",
        "cases",
        ["case_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "external_links",
        "simulation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_external_links_exactly_one_owner"),
        "external_links",
        "(simulation_id IS NOT NULL) <> (case_id IS NOT NULL)",
    )
    op.create_index(
        "uq_external_links_case_id_kind_url",
        "external_links",
        ["case_id", "kind", "url"],
        unique=True,
        postgresql_where=sa.text("case_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove case ownership support for external links."""
    connection = op.get_bind()
    case_owned_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM external_links WHERE case_id IS NOT NULL"
        )
    ).scalar_one()
    if case_owned_count:
        raise RuntimeError(
            "Downgrade blocked: external_links contains case-owned rows that "
            "cannot be represented after removing case ownership support."
        )

    op.drop_index("uq_external_links_case_id_kind_url", table_name="external_links")
    op.drop_constraint(
        op.f("ck_external_links_exactly_one_owner"),
        "external_links",
        type_="check",
    )
    op.alter_column(
        "external_links",
        "simulation_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint(
        op.f("fk_external_links_case_id_cases"),
        "external_links",
        type_="foreignkey",
    )
    op.drop_column("external_links", "case_id")
