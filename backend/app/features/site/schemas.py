from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel


class SiteCreate(CamelInBaseModel):
    """Schema for creating a site."""

    name: Annotated[str, Field(..., description="The display name of the site")]


class SiteOut(CamelOutBaseModel):
    """Schema for representing a site."""

    id: Annotated[UUID, Field(..., description="The unique identifier of the site")]
    name: Annotated[str, Field(..., description="The display name of the site")]
    created_at: Annotated[
        datetime, Field(..., description="The timestamp when the site was created")
    ]
    updated_at: Annotated[
        datetime, Field(..., description="The timestamp when the site was last updated")
    ]
