from uuid import UUID

from fastapi_users import schemas


class UserRead(schemas.BaseUser[UUID]):
    """Returned when reading a user (e.g. /users/me)."""

    role: str


class UserCreate(schemas.BaseUserCreate):
    """Used for registration (/auth/register)."""

    # Default to "user" on registration.
    role: str = "user"


class UserUpdate(schemas.BaseUserUpdate):
    """Used for user updates (/users/{id})."""

    # Optional for updates (admin can change roles)
    role: str | None = None
