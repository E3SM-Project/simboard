from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelInBaseModel, CamelOutBaseModel


class MachineCreate(CamelInBaseModel):
    name: str = Field(..., description="The name of the machine")
    site: str = Field(..., description="The site where the machine is located")
    architecture: str = Field(..., description="The architecture of the machine")
    scheduler: str = Field(..., description="The scheduler used by the machine")
    gpu: bool = Field(False, description="Indicates if the machine has a GPU")
    notes: str | None = Field(None, description="Additional notes about the machine")


class MachineOut(CamelOutBaseModel):
    id: UUID = Field(..., description="The unique identifier of the machine")

    name: str = Field(..., description="The name of the machine")
    site: str = Field(..., description="The site where the machine is located")
    architecture: str = Field(..., description="The architecture of the machine")
    scheduler: str = Field(..., description="The scheduler used by the machine")
    gpu: bool = Field(False, description="Indicates if the machine has a GPU")
    notes: str | None = Field(None, description="Additional notes about the machine")

    created_at: datetime = Field(
        ..., description="The timestamp when the machine was created"
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the machine was last updated"
    )
