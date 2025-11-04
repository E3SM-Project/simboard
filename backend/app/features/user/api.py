from fastapi import APIRouter, Depends

from app.core.config import settings
from app.features.user.manager import (
    current_active_superuser,
    current_active_user,
    fastapi_users,
)
from app.features.user.oauth import github_oauth_backend, github_oauth_client
from app.features.user.schemas import UserRead, UserUpdate

user_router = APIRouter(prefix="/users", tags=["users"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])

# --- GitHub OAuth Routes ---
auth_router.include_router(
    fastapi_users.get_oauth_router(
        github_oauth_client,
        github_oauth_backend,
        state_secret=settings.github_state_secret_key,
        redirect_url=settings.github_redirect_url,
        associate_by_email=True,
        is_verified_by_default=True,
    ),
    prefix="/github",
    tags=["auth"],
)


# --- USER ROUTES ---
# Users can manage their own profile.
user_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    tags=["users"],
    dependencies=[Depends(current_active_user)],
)

# --- ADMIN USER ROUTES ---
# Admins can manage all users.
user_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="",
    tags=["users"],
    dependencies=[Depends(current_active_superuser)],
)
