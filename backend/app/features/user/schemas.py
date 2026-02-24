from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr


class UserRead(schemas.BaseUser[UUID]):
    """Returned when reading a user (e.g. /users/me)."""

    role: Annotated[str, "The role of the user"]


class UserCreate(schemas.BaseUserCreate):
    """Used for registration (/auth/register)."""

    # Default to "user" on registration.
    role: Annotated[str, "The role of the user"] = "user"

    # password is optional for OAuth.
    password: Annotated[str | None, "The user's password"] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Used for user updates (/users/{id})."""

    # Optional for updates (admin can change roles)
    role: Annotated[str | None, "The role of the user"] = None


class UserPreview(BaseModel):
    """Minimal user info used for display purposes only."""

    id: UUID
    email: EmailStr
    role: str
    full_name: str | None = None

    model_config = {"from_attributes": True}


# API Token Schemas
# ~~~~~~~~~~~~~~~~~


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


# Service Account Schemas
# ~~~~~~~~~~~~~~~~~~~~~~~


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
