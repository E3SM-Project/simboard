from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel


class ApiTokenCreate(BaseModel):
    """Schema for creating an API token."""

    name: Annotated[str, "Human-readable identifier for the token"]
    user_id: Annotated[UUID, "User ID to associate with the token"]
    expires_at: Annotated[
        datetime | None, "Optional expiration datetime (timezone-aware)"
    ] = None


class ApiTokenCreated(BaseModel):
    """Schema for the response after creating an API token.

    This is the only time the raw token is returned.
    """

    id: UUID
    name: str
    token: Annotated[str, "Raw API token (returned only once)"]
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class ApiTokenRead(BaseModel):
    """Schema for reading an API token (without the raw token)."""

    id: UUID
    name: str
    user_id: UUID
    created_at: datetime
    expires_at: datetime | None
    revoked: bool

    model_config = {"from_attributes": True}
