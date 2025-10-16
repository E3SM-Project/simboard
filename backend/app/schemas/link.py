from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, HttpUrl

from app.schemas.base import CamelInBaseModel, CamelOutBaseModel


class ExternalLinkKind(str, Enum):
    """Enumeration of possible external link types."""

    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


class ExternalLinkCreate(CamelInBaseModel):
    kind: ExternalLinkKind = Field(..., description="The type of the external link.")
    url: HttpUrl = Field(..., description="The URL of the external link.")
    label: str | None = Field(
        None, description="An optional label for the external link."
    )


class ExternalLinkOut(CamelOutBaseModel):
    id: UUID = Field(..., description="The unique identifier of the external link.")

    kind: ExternalLinkKind = Field(..., description="The type of the external link.")
    url: HttpUrl = Field(..., description="The URL of the external link.")
    label: str | None = Field(
        None, description="An optional label for the external link."
    )

    created_at: datetime = Field(
        ..., description="The timestamp when the external link was created."
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the external link was last updated."
    )
