from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.artifact import Artifact
    from app.db.link import ExternalLink
    from app.db.machine import Machine


class Simulation(Base, IDMixin, TimestampMixin):
    __tablename__ = "simulations"

    # Configuration
    # ~~~~~~~~~~~~~~
    name: Mapped[str] = mapped_column(String(200), index=True, unique=True)
    case_name: Mapped[str] = mapped_column(String(200), index=True, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compset: Mapped[str] = mapped_column(String(120))
    compset_alias: Mapped[str] = mapped_column(String(120))
    grid_name: Mapped[str] = mapped_column(String(200))
    grid_resolution: Mapped[str] = mapped_column(String(50))
    parent_simulation_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id")
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), ForeignKey("status_lookup.code"), index=True
    )
    campaign_id: Mapped[str | None] = mapped_column(String(100))
    experiment_type_id: Mapped[str | None] = mapped_column(String(100))
    initialization_type: Mapped[str] = mapped_column(String(50))
    group_name: Mapped[str | None] = mapped_column(String(120))

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id"), index=True
    )
    simulation_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    simulation_end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    run_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compiler: Mapped[str | None] = mapped_column(String(100))

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: Mapped[str | None] = mapped_column(Text)
    known_issues: Mapped[str | None] = mapped_column(Text)
    notes_markdown: Mapped[str | None] = mapped_column(Text)

    # Version control
    # ~~~~~~~~~~~~~~~
    git_repository_url: Mapped[str | None] = mapped_column(String(500))
    git_branch: Mapped[str | None] = mapped_column(String(200))
    git_tag: Mapped[str | None] = mapped_column(String(100))
    git_commit_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: Mapped[str | None] = mapped_column(String(100))
    last_updated_by: Mapped[str | None] = mapped_column(String(100))

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    # ~~~~~~~~~~~~~
    machine: Mapped[Machine] = relationship(
        back_populates="simulations", foreign_keys=[machine_id]
    )
    parent: Mapped[Simulation] = relationship(remote_side="Simulation.id")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )
    links: Mapped[list[ExternalLink]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )

    # Constraints
    # ~~~~~~~~~~~
    __table_args__ = (
        UniqueConstraint("name", "git_tag", name="uq_simulation_name_tag"),
    )
