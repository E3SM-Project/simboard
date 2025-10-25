"""SQLAlchemy ORM models for simulations and related entities."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.features.machine.models import Machine


class Status(Base):
    __tablename__ = "status_lookup"
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class ArtifactKind(str, Enum):
    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESSING_SCRIPT = "postprocessing_script"


class ExternalLinkKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


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
