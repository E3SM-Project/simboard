from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from httpx_oauth.clients.github import GitHubOAuth2

from app.core.config import settings

# Cookie transport setup for OAuth.
cookie_transport = CookieTransport(
    cookie_name=settings.cookie_name,
    cookie_max_age=settings.cookie_max_age,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite=settings.cookie_samesite,
)

# GitHub OAuth2 client setup.
github_oauth_client = GitHubOAuth2(
    client_id=settings.github_client_id,
    client_secret=settings.github_client_secret,
    scopes=["read:user", "user:email"],
)


def get_jwt_strategy() -> JWTStrategy:
    """Return JWT strategy for OAuth backend."""
    return JWTStrategy(secret=settings.github_state_secret_key, lifetime_seconds=3600)


# OAuth backend definition.
# For OAuth, the backend mainly defines the transport (cookie) and name.
github_oauth_backend: AuthenticationBackend = AuthenticationBackend(
    name="github", transport=cookie_transport, get_strategy=get_jwt_strategy
)
