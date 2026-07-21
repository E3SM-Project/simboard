from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel


class MachineCreate(CamelInBaseModel):
    """Schema for creating a new Machine."""

    name: Annotated[str, Field(..., description="The name of the machine")]
    site: Annotated[
        str | None,
        Field(None, description="The site where the machine is located"),
    ]
    site_id: Annotated[
        UUID | None,
        Field(None, description="The identifier of the machine's site"),
    ]
    architecture: Annotated[
        str, Field(..., description="The architecture of the machine")
    ]
    scheduler: Annotated[
        str, Field(..., description="The scheduler used by the machine")
    ]
    gpu: Annotated[bool, Field(False, description="Indicates if the machine has a GPU")]
    notes: Annotated[
        str | None, Field(None, description="Additional notes about the machine")
    ]

    @model_validator(mode="after")
    def validate_site_reference(self) -> "MachineCreate":
        if self.site is None and self.site_id is None:
            raise ValueError("Either site or siteId is required")
        return self


class MachineOut(CamelOutBaseModel):
    """Schema for representing a Machine object."""

    id: Annotated[UUID, Field(..., description="The unique identifier of the machine")]

    name: Annotated[str, Field(..., description="The name of the machine")]
    site: Annotated[
        str, Field(..., description="The site where the machine is located")
    ]
    site_id: Annotated[
        UUID, Field(..., description="The identifier of the machine's site")
    ]
    architecture: Annotated[
        str, Field(..., description="The architecture of the machine")
    ]
    scheduler: Annotated[
        str, Field(..., description="The scheduler used by the machine")
    ]
    gpu: Annotated[bool, Field(False, description="Indicates if the machine has a GPU")]
    notes: Annotated[
        str | None, Field(None, description="Additional notes about the machine")
    ]

    created_at: Annotated[
        datetime, Field(..., description="The timestamp when the machine was created")
    ]
    updated_at: Annotated[
        datetime,
        Field(..., description="The timestamp when the machine was last updated"),
    ]
