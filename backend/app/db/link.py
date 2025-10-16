from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.simulation import Simulation


class ExternalLinkKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


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

    simulation: Mapped["Simulation"] = relationship(
        back_populates="links",
        primaryjoin="ExternalLink.simulation_id==Simulation.id",
        passive_deletes=True,
    )
