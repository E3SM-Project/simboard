"""Backward-compatible schema exports for the user feature."""

from app.features.user.schemas.schemas_service_account import (
    ServiceAccountCreate,
    ServiceAccountResponse,
)
from app.features.user.schemas.schemas_token import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
)
from app.features.user.schemas.schemas_user import (
    UserCreate,
    UserPreview,
    UserRead,
    UserUpdate,
)

__all__ = [
    "UserRead",
    "UserCreate",
    "UserUpdate",
    "UserPreview",
    "ApiTokenCreate",
    "ApiTokenCreated",
    "ApiTokenRead",
    "ServiceAccountCreate",
    "ServiceAccountResponse",
]
