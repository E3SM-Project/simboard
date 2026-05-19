from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import Response
from fastapi.responses import RedirectResponse
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from httpx_oauth.clients.github import GitHubOAuth2

from app.core.config import settings
from app.features.user.auth.utils import get_jwt_strategy

DEFAULT_POST_LOGIN_REDIRECT_PATH = "/"


def normalize_post_login_return_to(return_to: str | None) -> str | None:
    if not return_to:
        return None

    try:
        parsed = urlparse(return_to)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    target_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if target_origin not in settings.frontend_origins_list:
        return None

    path = parsed.path or DEFAULT_POST_LOGIN_REDIRECT_PATH
    if not path.startswith("/") or path.startswith("//"):
        return None
    if path == "/auth/callback":
        return None

    return return_to


def build_frontend_auth_redirect_url(return_to: str | None = None) -> str:
    redirect_url = settings.frontend_auth_redirect_url
    normalized_return_to = normalize_post_login_return_to(return_to)
    if normalized_return_to is None:
        return redirect_url

    parsed_redirect_url = urlparse(redirect_url)
    query_pairs = parse_qsl(parsed_redirect_url.query, keep_blank_values=True)
    query_pairs = [(key, value) for key, value in query_pairs if key != "return_to"]
    query_pairs.append(("return_to", normalized_return_to))

    return urlunparse(
        parsed_redirect_url._replace(query=urlencode(query_pairs, doseq=True))
    )


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
        response = RedirectResponse(build_frontend_auth_redirect_url(), status_code=302)

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
