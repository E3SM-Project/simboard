from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base
from app.common.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.features.machine.models import Machine


class Site(Base, IDMixin, TimestampMixin):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    machines: Mapped[list[Machine]] = relationship(back_populates="site_record")
