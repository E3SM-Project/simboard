import uuid

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_async import get_async_session
from app.core.logger import _setup_custom_logger
from app.features.user.models import OAuthAccount, User
from app.features.user.oauth import github_oauth_backend

logger = _setup_custom_logger(__name__)


async def get_user_db(session: AsyncSession = Depends(get_async_session)):  # noqa: B008
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(self, user: User, request=None):
        logger.info(f"✅ New GitHub user registered: {user.email}")


async def get_user_manager(user_db=Depends(get_user_db)):  # noqa: B008
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [github_oauth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)
