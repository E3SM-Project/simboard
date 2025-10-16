from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import AnyUrl, Field

from app.schemas.base import CamelInBaseModel, CamelOutBaseModel


class ArtifactKind(str, Enum):
    """Enumeration of possible artifact types."""

    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESS_SCRIPT = "postprocessing_script"


class ArtifactCreate(CamelInBaseModel):
    kind: ArtifactKind = Field(..., description="The type of the artifact.")
    uri: AnyUrl = Field(..., description="The URI where the artifact is located.")
    label: str | None = Field(None, description="An optional label for the artifact.")


class ArtifactOut(CamelOutBaseModel):
    id: UUID = Field(..., description="The unique identifier of the artifact.")

    kind: ArtifactKind = Field(..., description="The type of the artifact.")
    uri: AnyUrl = Field(..., description="The URI where the artifact is located.")
    label: str | None = Field(None, description="An optional label for the artifact.")

    created_at: datetime = Field(
        ..., description="The timestamp when the artifact was created."
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the artifact was last updated."
    )
