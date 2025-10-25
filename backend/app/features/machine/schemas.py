from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel


class MachineCreate(CamelInBaseModel):
    """Schema for creating a new Machine."""

    name: Annotated[str, Field(..., description="The name of the machine")]
    site: Annotated[
        str, Field(..., description="The site where the machine is located")
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


class MachineOut(CamelOutBaseModel):
    """Schema for representing a Machine object."""

    id: Annotated[UUID, Field(..., description="The unique identifier of the machine")]

    name: Annotated[str, Field(..., description="The name of the machine")]
    site: Annotated[
        str, Field(..., description="The site where the machine is located")
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
