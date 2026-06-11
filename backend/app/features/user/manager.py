import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database_async import get_async_session
from app.core.logger import _setup_custom_logger
from app.features.user.auth.oauth import GITHUB_OAUTH_BACKEND
from app.features.user.auth.token import JWT_BEARER_BACKEND, validate_token
from app.features.user.models import OAuthAccount, User, UserRole

logger = _setup_custom_logger(__name__)


async def get_user_db(session: AsyncSession = Depends(get_async_session)):  # noqa: B008
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(self, user: User, request=None):
        logger.info(f"✅ New GitHub user registered: {user.email}")

    async def refresh_github_org_membership(
        self,
        user: User,
        *,
        is_verified_member: bool,
        checked_at: datetime | None = None,
    ) -> User:
        membership_checked_at = checked_at or datetime.now(timezone.utc)

        return await self.user_db.update(
            user,
            {
                "has_verified_e3sm_membership": is_verified_member,
                "github_org_membership_checked_at": membership_checked_at,
            },
        )


async def get_user_manager(user_db=Depends(get_user_db)):  # noqa: B008
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager, [GITHUB_OAUTH_BACKEND, JWT_BEARER_BACKEND]
)

_oauth_current_active_user = fastapi_users.current_user(active=True, optional=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)


async def current_active_user(
    request: Request,
    oauth_user: Optional[User] = Depends(_oauth_current_active_user),  # noqa: B008
    db: Session = Depends(get_database_session),  # noqa: B008
) -> User:
    """
    Unified authentication dependency that supports both OAuth and API tokens.

    Authentication precedence:
    1. OAuth/JWT authentication (existing behavior)
    2. API token authentication (Bearer token fallback)

    If OAuth authentication succeeds, the OAuth user is returned.
    If OAuth fails, attempts to validate a Bearer token from the Authorization header.
    If both fail, raises 401 Unauthorized.

    Parameters
    ----------
    request : Request
        FastAPI request object
    oauth_user : Optional[User]
        User from OAuth authentication (optional)
    db : Session
        Database session for token validation

    Returns
    -------
    User
        Authenticated user from either OAuth or API token

    Raises
    ------
    HTTPException
        401 Unauthorized if neither authentication method succeeds
    """
    if oauth_user is not None:
        return oauth_user

    user = _resolve_api_token_user(request, db, allow_missing=False)
    assert user is not None

    return user


async def optional_current_user(
    request: Request,
    oauth_user: Optional[User] = Depends(_oauth_current_active_user),  # noqa: B008
    db: Session = Depends(get_database_session),  # noqa: B008
) -> Optional[User]:
    """Optional auth dependency supporting OAuth and API tokens."""

    if oauth_user is not None:
        return oauth_user

    return _resolve_api_token_user(request, db, allow_missing=True)


def can_edit_managed_content(user: User | None) -> bool:
    """Return whether user may edit human-managed SimBoard content."""

    if user is None:
        return False

    if user.role == UserRole.ADMIN:
        return True

    return user.role == UserRole.USER and user.has_verified_e3sm_membership


def _resolve_api_token_user(
    request: Request,
    db: Session,
    *,
    allow_missing: bool,
) -> Optional[User]:
    """Resolve Bearer API-token auth, optionally allowing missing credentials."""

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        if allow_missing:
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    token = parts[1]
    user = validate_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return user
