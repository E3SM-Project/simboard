from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.features.simulation.models import Simulation


class Machine(Base, IDMixin, TimestampMixin):
    __tablename__ = "machines"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    site: Mapped[str] = mapped_column(String(200))
    architecture: Mapped[str] = mapped_column(String(100))
    scheduler: Mapped[str] = mapped_column(String(100))
    gpu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    simulations: Mapped[list[Simulation]] = relationship(
        back_populates="machine", cascade="all,save-update"
    )
