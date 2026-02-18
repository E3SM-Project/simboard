"""SQLAlchemy ORM models for ingestion audit records."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus


class Ingestion(Base):
    """Audit record for ingestion events (upload or path-based)."""

    __tablename__ = "ingestions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4, index=True
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
        UUID(as_uuid=True),
        ForeignKey("machines.id"),
        nullable=False,
        index=True,
    )
    triggered_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
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

    user = relationship("User")

    def __repr__(self) -> str:
        return f"<Ingestion id={self.id} source_type={self.source_type!r} status={self.status!r}>"
