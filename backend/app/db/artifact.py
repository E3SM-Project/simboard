from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.simulation import Simulation


class ArtifactKind(str, Enum):
    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESSING_SCRIPT = "postprocessing_script"


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
