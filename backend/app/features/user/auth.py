"""Authentication backend setup using FastAPI Users with JWT and cookie transport."""

from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from app.core.config import settings


def get_jwt_strategy() -> JWTStrategy:
    """JWT strategy for short-lived access tokens."""
    return JWTStrategy(
        secret=settings.jwt_secret_key,
        lifetime_seconds=settings.lifetime_seconds,
    )


# Cookie transport configuration for storing JWT in cookies.
cookie_transport = CookieTransport(
    cookie_name=settings.cookie_name,
    cookie_max_age=settings.cookie_max_age,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=settings.cookie_httponly,
    cookie_samesite=settings.cookie_samesite,
)

# Authentication backend combining cookie transport and JWT strategy.
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
