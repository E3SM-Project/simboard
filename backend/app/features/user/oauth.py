from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    Strategy,
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


class NoOpStrategy(Strategy):
    # A no-operation strategy for GitHub OAuth.
    async def read_token(self, token, user_manager):
        return None

    async def write_token(self, user):
        return ""

    async def destroy_token(self, token, user):
        return None


def get_noop_strategy():
    return NoOpStrategy()


# OAuth backend definition.
# For OAuth, the backend mainly defines the transport (cookie) and name.
# No strategy is required here — OAuth router handles login flow.
github_oauth_backend: AuthenticationBackend = AuthenticationBackend(
    name="github", transport=cookie_transport, get_strategy=NoOpStrategy
)
