"""Authentication backend setup using FastAPI Users with JWT and cookie transport."""

from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from app.core.config import settings

cookie_transport = CookieTransport(
    cookie_name="simscope_auth",  # name of cookie
    cookie_max_age=3600,  # seconds (1h)
    cookie_secure=False,  # set to True in production (HTTPS)
    cookie_httponly=True,  # prevents JS access
    cookie_samesite="lax",  # can use "strict" or "none" if needed
)


def get_jwt_strategy() -> JWTStrategy:
    """Get the JWT strategy for authentication."""
    return JWTStrategy(
        secret=settings.jwt_secret_key,  # e.g. read from env
        lifetime_seconds=3600,  # token lifetime (1h)
    )


# Authentication backend using JWT strategy and cookie transport.
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
