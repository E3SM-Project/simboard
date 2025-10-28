from typing import Annotated
from uuid import UUID

from fastapi_users import schemas


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
