from fastapi import Response
from fastapi.responses import RedirectResponse
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from httpx_oauth.clients.github import GitHubOAuth2

from app.core.config import settings
from app.features.user.auth.utils import get_jwt_strategy


class CustomCookieTransport(CookieTransport):
    """Custom cookie transport to handle OAuth login responses."""

    async def get_login_response(self, token: str) -> Response:
        """Create a login response that sets the cookie and redirects to frontend.

        The default response is a 204 with no content, which is not suitable for
        OAuth flows where we need to redirect the user after login.

        Source: https://github.com/fastapi-users/fastapi-users/issues/434#issuecomment-1881945184

        Parameters:
            token (str): The JWT token to set in the cookie.
        Returns:
            Response: The HTTP response with the cookie set and redirection.
        """
        response = RedirectResponse(
            settings.frontend_auth_redirect_url, status_code=302
        )

        return self._set_login_cookie(response, token)


COOKIE_TRANSPORT = CustomCookieTransport(
    cookie_name=settings.cookie_name,
    cookie_max_age=settings.cookie_max_age,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=settings.cookie_httponly,
    cookie_samesite=settings.cookie_samesite,
)

GITHUB_OAUTH_CLIENT = GitHubOAuth2(
    client_id=settings.github_client_id,
    client_secret=settings.github_client_secret,
    scopes=["read:user", "user:email"],
)

GITHUB_OAUTH_BACKEND: AuthenticationBackend = AuthenticationBackend(
    name="github", transport=COOKIE_TRANSPORT, get_strategy=get_jwt_strategy
)
