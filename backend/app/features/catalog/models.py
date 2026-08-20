"""SQLAlchemy ORM models for executions and related entities."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin
from app.features.catalog.enums import (
    ArtifactKind,
    ExecutionStatus,
    ExternalLinkKind,
    SimulationType,
)

if TYPE_CHECKING:
    from app.features.ingestion.models import Ingestion
    from app.features.machine.models import Machine
    from app.features.user.models import User


class Case(Base, IDMixin, TimestampMixin):
    """A logical experiment grouped by case name.

    Each Case contains one or more executions.
    """

    __tablename__ = "cases"

    __table_args__ = (
        UniqueConstraint(
            "name",
            "machine_id",
            "hpc_username",
            name="uq_cases_name_machine_id_hpc_username",
        ),
    )

    name: Mapped[str] = mapped_column(Text, index=True)
    machine_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("machines.id"), index=True, nullable=False
    )
    hpc_username: Mapped[str] = mapped_column(String(200), nullable=False)
    case_group: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    machine: Mapped[Machine] = relationship("Machine", foreign_keys=[machine_id])
    executions: Mapped[list[Execution]] = relationship(
        "Execution",
        back_populates="case",
        foreign_keys="Execution.case_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    links: Mapped[list[ExternalLink]] = relationship(
        "ExternalLink",
        back_populates="case",
        foreign_keys="ExternalLink.case_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Execution(Base, IDMixin, TimestampMixin):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "execution_id",
            name="uq_executions_case_id_execution_id",
        ),
        CheckConstraint(
            "compute_type IS NULL OR compute_type IN ('cpu', 'gpu')",
            name="compute_type",
        ),
    )

    # Configuration
    # ~~~~~~~~~~~~~~
    case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    case_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compset: Mapped[str] = mapped_column(String(120))
    compset_alias: Mapped[str] = mapped_column(Text)
    grid_name: Mapped[str] = mapped_column(Text)
    grid_resolution: Mapped[str] = mapped_column(Text)

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
    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(
            ExecutionStatus,
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

    # Model timeline
    # ~~~~~~~~~~~~~~
    simulation_start_date: Mapped[date] = mapped_column(Date)
    simulation_end_date: Mapped[date | None] = mapped_column(Date)
    run_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compiler: Mapped[str | None] = mapped_column(String(100))
    compute_type: Mapped[Literal["cpu", "gpu"] | None] = mapped_column(
        String(3), nullable=True
    )

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
        PG_UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    last_updated_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    ingestion_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ingestions.id"), index=True, nullable=False
    )
    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    # ~~~~~~~~~~~~~
    case: Mapped[Case] = relationship(
        "Case", back_populates="executions", foreign_keys=[case_id]
    )
    created_by_user = relationship("User", foreign_keys=[created_by], lazy="joined")
    last_updated_by_user = relationship(
        "User", foreign_keys=[last_updated_by], lazy="joined"
    )
    ingestion: Mapped[Ingestion] = relationship(
        "Ingestion", back_populates="executions"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )
    links: Mapped[list[ExternalLink]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )


class MetadataChange(Base, IDMixin):
    """One append-only field change made through a managed metadata edit."""

    __tablename__ = "metadata_changes"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('case', 'execution')",
            name="entity_type",
        ),
        Index(
            "ix_metadata_changes_entity_history",
            "entity_type",
            "entity_id",
            "changed_at",
            "id",
        ),
    )

    entity_type: Mapped[Literal["case", "execution"]] = mapped_column(
        String(20), nullable=False
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    editor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    editor: Mapped[User] = relationship("User", foreign_keys=[editor_id], lazy="joined")


class Artifact(Base, IDMixin, TimestampMixin):
    __tablename__ = "artifacts"

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    kind: Mapped[ArtifactKind] = mapped_column(
        SAEnum(
            ArtifactKind,
            name="artifact_kind_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        comment=f"Must be one of: {', '.join([e.value for e in ArtifactKind])}",
    )
    uri: Mapped[str] = mapped_column(String(1000))
    label: Mapped[Optional[str]] = mapped_column(String(200))
    checksum: Mapped[Optional[str]] = mapped_column(String(128))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    execution: Mapped[Execution] = relationship(
        back_populates="artifacts",
        primaryjoin="Artifact.execution_id==Execution.id",
        passive_deletes=True,
    )


class ExternalLink(Base, IDMixin, TimestampMixin):
    __tablename__ = "external_links"
    __table_args__ = (
        CheckConstraint(
            "(execution_id IS NOT NULL) <> (case_id IS NOT NULL)",
            name="exactly_one_owner",
        ),
        Index(
            "uq_external_links_case_id_kind_url",
            "case_id",
            "kind",
            "url",
            unique=True,
            postgresql_where=text("case_id IS NOT NULL"),
        ),
    )

    execution_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=True,
    )
    case_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
    )

    kind: Mapped[ExternalLinkKind] = mapped_column(
        SAEnum(
            ExternalLinkKind,
            name="external_link_kind_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        comment=f"Must be one of: {', '.join([e.value for e in ExternalLinkKind])}",
    )
    url: Mapped[str] = mapped_column(String(1000))
    label: Mapped[Optional[str]] = mapped_column(String(200))

    execution: Mapped[Execution | None] = relationship(
        back_populates="links",
        primaryjoin="ExternalLink.execution_id==Execution.id",
        foreign_keys=[execution_id],
        passive_deletes=True,
    )
    case: Mapped[Case | None] = relationship(
        back_populates="links",
        primaryjoin="ExternalLink.case_id==Case.id",
        foreign_keys=[case_id],
        passive_deletes=True,
    )
    diagnostic_provenance_state: Mapped[DiagnosticProvenanceState | None] = (
        relationship(
            back_populates="link",
            cascade="all, delete-orphan",
            passive_deletes=True,
            uselist=False,
        )
    )


class DiagnosticProvenanceState(Base, IDMixin):
    """Successful scanner submission state for one published diagnostics link."""

    __tablename__ = "diagnostic_provenance_states"
    __table_args__ = (
        UniqueConstraint(
            "machine_name",
            "archive_relative_case_path",
            name="uq_diagnostic_provenance_states_machine_path",
        ),
        UniqueConstraint("link_id", name="uq_diagnostic_provenance_states_link_id"),
    )

    link_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("external_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    machine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    archive_relative_case_path: Mapped[str] = mapped_column(Text, nullable=False)
    settings_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    provenance_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    linked_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    link: Mapped[ExternalLink] = relationship(
        back_populates="diagnostic_provenance_state",
        foreign_keys=[link_id],
        passive_deletes=True,
    )
