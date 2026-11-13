"""SQLAlchemy ORM models for ingestion audit records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.features.ingestion.enums import (
    ExecutionDiscoveryOutcome,
    IngestionSourceType,
    IngestionStatus,
    ScheduledJobFailureReason,
    ScheduledJobRunStatus,
)

FAILURE_MESSAGE_MAX_LENGTH = 500

if TYPE_CHECKING:
    from app.features.catalog.models import Execution


class Ingestion(Base):
    """Audit record for ingestion events (upload or path-based)."""

    __tablename__ = "ingestions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )

    source_type: Mapped[IngestionSourceType] = mapped_column(
        SAEnum(
            IngestionSourceType,
            name="ingestion_source_type_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        nullable=False,
    )
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    machine_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("machines.id"),
        nullable=False,
        index=True,
    )
    triggered_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(
            IngestionStatus,
            name="ingestion_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        nullable=False,
    )
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archive_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_execution_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True
    )

    user = relationship("User")
    executions: Mapped[list[Execution]] = relationship(
        "Execution", back_populates="ingestion"
    )

    def __repr__(self) -> str:
        return f"<Ingestion id={self.id} source_type={self.source_type!r} status={self.status!r}>"


class ExecutionDiscoveryResult(Base):
    """Validation result for one identity; rejected results can be refreshed."""

    __tablename__ = "execution_discovery_results"
    __table_args__ = (
        UniqueConstraint(
            "machine_id",
            "case_identity",
            "execution_id",
            name="uq_execution_discovery_result_identity",
        ),
        Index(
            "ix_execution_discovery_results_lookup",
            "machine_id",
            "case_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    machine_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False
    )
    case_identity: Mapped[str] = mapped_column(Text, nullable=False)
    execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[ExecutionDiscoveryOutcome] = mapped_column(
        SAEnum(
            ExecutionDiscoveryOutcome,
            name="execution_discovery_outcome_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        nullable=False,
    )
    errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class ArchiveScanCheckpoint(Base):
    """Completed scan of one immutable archive snapshot."""

    __tablename__ = "archive_scan_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "machine_id",
            "archive_name",
            "archive_month",
            "snapshot_name",
            name="uq_archive_scan_checkpoint_identity",
        ),
        Index(
            "ix_archive_scan_checkpoints_lookup",
            "machine_id",
            "archive_name",
            "archive_month",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    machine_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False
    )
    archive_name: Mapped[str] = mapped_column(Text, nullable=False)
    archive_month: Mapped[str] = mapped_column(String(7), nullable=False)
    snapshot_name: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class ScheduledJob(Base):
    """Registered scheduled job, its reporting account, and health thresholds."""

    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    machine_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False, index=True
    )
    scan_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    # Only this service account may report runs for the job.
    service_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    max_silence_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    machine = relationship("Machine")


class ScheduledJobRun(Base):
    """One scheduled job run, identified by a client-generated run ID."""

    __tablename__ = "scheduled_job_runs"
    __table_args__ = (
        Index("ix_scheduled_job_runs_job_reported", "job_id", "reported_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ScheduledJobRunStatus] = mapped_column(
        SAEnum(
            ScheduledJobRunStatus,
            name="scheduled_job_run_status_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        nullable=False,
    )
    # Client-supplied execution times.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Server-observed report times; health freshness uses only these.
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finish_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[ScheduledJobFailureReason | None] = mapped_column(
        SAEnum(
            ScheduledJobFailureReason,
            name="scheduled_job_failure_reason_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=True,
        ),
        nullable=True,
    )
    failure_message: Mapped[str | None] = mapped_column(
        String(FAILURE_MESSAGE_MAX_LENGTH), nullable=True
    )
    failure_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_transient: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Client-reported case uploads that failed after retries; NULL when none.
    upload_failures: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
