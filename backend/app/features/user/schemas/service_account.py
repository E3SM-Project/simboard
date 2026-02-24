from typing import Annotated
from uuid import UUID

from pydantic import BaseModel


class ServiceAccountCreate(BaseModel):
    """Schema for creating a SERVICE_ACCOUNT user via REST."""

    service_name: Annotated[
        str, "Name used to derive email as {service_name}@{settings.domain}"
    ]


class ServiceAccountResponse(BaseModel):
    """Response from the service account creation endpoint."""

    id: UUID
    email: str
    role: str
    created: Annotated[bool, "True if newly created, False if already existed"]

    model_config = {"from_attributes": True}
