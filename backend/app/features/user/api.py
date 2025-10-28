from fastapi import APIRouter, Depends

from app.features.user.auth import auth_backend
from app.features.user.manager import (
    current_active_superuser,
    current_active_user,
    fastapi_users,
)
from app.features.user.schemas import UserCreate, UserRead, UserUpdate

auth_router = APIRouter()
user_router = APIRouter()

# --- AUTHENTICATION & REGISTRATION ROUTES ---
# These are public (registration, login, logout, verify, etc.).
auth_router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
auth_router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
auth_router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
auth_router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

# --- USER ROUTES ---
# Users can manage their own profile.
user_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/me",
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
