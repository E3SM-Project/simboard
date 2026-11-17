from fastapi_users.authentication import JWTStrategy

from app.core.config import settings


def get_jwt_strategy() -> JWTStrategy:
    """Return JWT strategy for authentication backends.

    Returns
    -------
    JWTStrategy
        The JWT strategy configured with the secret key and token lifetime.
    """
    strategy: JWTStrategy = JWTStrategy(
        secret=settings.github_state_secret_key,
        lifetime_seconds=settings.cookie_max_age,
    )

    return strategy
