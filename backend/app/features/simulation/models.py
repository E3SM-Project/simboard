"""SQLAlchemy ORM models for simulations and related entities."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin
from app.features.simulation.enums import (
    ArtifactKind,
    ExternalLinkKind,
    SimulationStatus,
    SimulationType,
)

if TYPE_CHECKING:
    from app.features.machine.models import Machine


class Simulation(Base, IDMixin, TimestampMixin):
    __tablename__ = "simulations"

    # Configuration
    # ~~~~~~~~~~~~~~
    name: Mapped[str] = mapped_column(String(200), index=True)
    case_name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compset: Mapped[str] = mapped_column(String(120))
    compset_alias: Mapped[str] = mapped_column(Text)
    grid_name: Mapped[str] = mapped_column(Text)
    grid_resolution: Mapped[str] = mapped_column(Text)
    parent_simulation_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id")
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    simulation_type: Mapped[SimulationType] = mapped_column(
        SAEnum(
            SimulationType,
            name="simulation_type_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        )
    )
    status: Mapped[SimulationStatus] = mapped_column(
        SAEnum(
            SimulationStatus,
            name="simulation_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        index=True,
        nullable=False,
    )
    campaign: Mapped[str | None] = mapped_column(Text)
    experiment_type: Mapped[str | None] = mapped_column(Text)
    initialization_type: Mapped[str] = mapped_column(String(50))
    group_name: Mapped[str | None] = mapped_column(Text)

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
    git_repository_url: Mapped[str | None] = mapped_column(Text)
    git_branch: Mapped[str | None] = mapped_column(String(200))
    git_tag: Mapped[str | None] = mapped_column(String(100))
    git_commit_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    last_updated_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    # ~~~~~~~~~~~~~
    created_by_user = relationship("User", foreign_keys=[created_by], lazy="joined")
    last_updated_by_user = relationship(
        "User", foreign_keys=[last_updated_by], lazy="joined"
    )

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
        UniqueConstraint(
            "case_name",
            "machine_id",
            "simulation_start_date",
            name="uq_simulation_case_machine_date",
        ),
    )


class Artifact(Base, IDMixin, TimestampMixin):
    __tablename__ = "artifacts"

    simulation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    kind: Mapped[ArtifactKind] = mapped_column(
        SAEnum(
            ArtifactKind,
            name="artifact_kind_enum",
            native_enum=False,  # creates CHECK constraint instead of DB enum
            values_callable=lambda obj: [e.value for e in obj],  # use values not names
            validate_strings=True,  # ensures Python-side validation
        ),
        comment=f"Must be one of: {', '.join([e.value for e in ArtifactKind])}",
    )
    uri: Mapped[str] = mapped_column(String(1000))
    label: Mapped[Optional[str]] = mapped_column(String(200))
    checksum: Mapped[Optional[str]] = mapped_column(String(128))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    simulation: Mapped[Simulation] = relationship(
        back_populates="artifacts",
        primaryjoin="Artifact.simulation_id==Simulation.id",
        passive_deletes=True,
    )


class ExternalLink(Base, IDMixin, TimestampMixin):
    __tablename__ = "external_links"

    simulation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id", ondelete="CASCADE")
    )

    kind: Mapped[ExternalLinkKind] = mapped_column(
        SAEnum(
            ExternalLinkKind,
            name="external_link_kind_enum",
            native_enum=False,  # creates CHECK constraint instead of DB enum
            values_callable=lambda obj: [e.value for e in obj],  # use values not names
            validate_strings=True,  # ensures Python-side validation
        ),
        comment=f"Must be one of: {', '.join([e.value for e in ExternalLinkKind])}",
    )
    url: Mapped[str] = mapped_column(String(1000))
    label: Mapped[Optional[str]] = mapped_column(String(200))

    simulation: Mapped[Simulation] = relationship(
        back_populates="links",
        primaryjoin="ExternalLink.simulation_id==Simulation.id",
        passive_deletes=True,
    )
