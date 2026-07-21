from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.features.site.models import Site


class Machine(Base, IDMixin, TimestampMixin):
    __tablename__ = "machines"

    name: Mapped[str] = mapped_column(String(200))
    site_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sites.id"), index=True, nullable=False
    )
    architecture: Mapped[str] = mapped_column(String(100))
    scheduler: Mapped[str] = mapped_column(String(100))
    gpu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    site_record: Mapped[Site] = relationship(back_populates="machines", lazy="joined")

    @property
    def site(self) -> str:
        """Return site name for backwards-compatible API serialization."""
        return self.site_record.name

    __table_args__ = (
        CheckConstraint(
            "name = lower(name)",
            name=conv("ck_machines_name_lowercase"),
        ),
        Index("uq_machines_name_lower", func.lower(name), unique=True),
    )
