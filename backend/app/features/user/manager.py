"""User management setup using FastAPI Users."""

from uuid import UUID

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.user.authentication import authentication_backend
from app.features.user.models import OAuthAccount, User
from core.database_async import get_async_session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):  # noqa: B008
    """Get the user database dependency."""
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """User manager for handling user operations."""

    reset_password_token_secret = settings.reset_password_secret_key
    verification_token_secret = settings.verification_secret_key


async def get_user_manager(user_db=Depends(get_user_db)):  # noqa: B008
    """Get the user manager dependency."""
    yield UserManager(user_db)


# --- FastAPI Users Setup ---
fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [authentication_backend])

# Helpers for route dependencies
current_user = fastapi_users.current_user()
current_active_user = fastapi_users.current_user(active=True)
current_verified_user = fastapi_users.current_user(verified=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
