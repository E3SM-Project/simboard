from fastapi_users.authentication import JWTStrategy

from app.core.config import settings

# Admin password-login bearer JWTs stay short-lived; they are returned as JSON
# and carry superuser privileges.
BEARER_JWT_LIFETIME_SECONDS = 3600


def get_jwt_strategy() -> JWTStrategy:
    """Return JWT strategy for browser (GitHub OAuth cookie) logins.

    Returns
    -------
    JWTStrategy
        The JWT strategy configured with the secret key and the auth cookie
        lifetime.
    """
    strategy: JWTStrategy = JWTStrategy(
        secret=settings.github_state_secret_key,
        lifetime_seconds=settings.cookie_max_age,
    )

    return strategy


def get_bearer_jwt_strategy() -> JWTStrategy:
    """Return JWT strategy for password-login bearer tokens.

    Returns
    -------
    JWTStrategy
        The JWT strategy configured with the secret key and a fixed short
        lifetime.
    """
    strategy: JWTStrategy = JWTStrategy(
        secret=settings.github_state_secret_key,
        lifetime_seconds=BEARER_JWT_LIFETIME_SECONDS,
    )

    return strategy
