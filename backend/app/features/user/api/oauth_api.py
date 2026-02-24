from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.features.user.auth.oauth import GITHUB_OAUTH_BACKEND, GITHUB_OAUTH_CLIENT
from app.features.user.auth.token_auth import JWT_BEARER_BACKEND
from app.features.user.manager import (
    current_active_user,
    fastapi_users,
)
from app.features.user.schemas import UserRead, UserUpdate

user_router = APIRouter(prefix="/users", tags=["users"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])

# --- GitHub OAuth Routes ---
auth_router.include_router(
    fastapi_users.get_oauth_router(
        GITHUB_OAUTH_CLIENT,
        GITHUB_OAUTH_BACKEND,
        state_secret=settings.github_state_secret_key,
        redirect_url=settings.github_redirect_url,
        associate_by_email=True,
        is_verified_by_default=True,
    ),
    prefix="/github",
)

# --- JWT Login Routes ---
auth_router.include_router(
    fastapi_users.get_auth_router(JWT_BEARER_BACKEND),
    prefix="/jwt",
)


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout():
    """Log out the current user by clearing the authentication cookie."""
    response = JSONResponse(
        content={"message": "Successfully logged out"},
        status_code=status.HTTP_200_OK,
    )
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    return response


# --- USER ROUTES ---
# Users can manage their own profile; /{id} routes require superuser internally.
user_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    tags=["users"],
    dependencies=[Depends(current_active_user)],
)
