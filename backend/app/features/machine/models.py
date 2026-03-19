from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.features.simulation.models import Simulation


class Machine(Base, IDMixin, TimestampMixin):
    __tablename__ = "machines"

    name: Mapped[str] = mapped_column(String(200))
    site: Mapped[str] = mapped_column(String(200))
    architecture: Mapped[str] = mapped_column(String(100))
    scheduler: Mapped[str] = mapped_column(String(100))
    gpu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "name = lower(name)",
            name=conv("ck_machines_name_lowercase"),
        ),
        Index("uq_machines_name_lower", func.lower(name), unique=True),
    )

    simulations: Mapped[list[Simulation]] = relationship(
        back_populates="machine", cascade="all,save-update"
    )
