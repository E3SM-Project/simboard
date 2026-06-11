from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException, status
from fastapi.dependencies.models import Dependant
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.router.oauth import STATE_TOKEN_AUDIENCE, decode_jwt
from httpx import AsyncClient, HTTPError
from starlette.requests import Request

from app.api.version import API_BASE
from app.core.config import settings
from app.features.user.api import oauth
from app.features.user.manager import current_active_user
from app.features.user.models import UserRole
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_overrides() -> Generator[None, None, None]:
    """Automatically clear dependency overrides after every test."""
    yield

    app.dependency_overrides.clear()


def override_dependency(path: str, name_contains: str, override) -> None:
    """Find and override a dependency in a route by partial function name."""
    for route in app.routes:
        if isinstance(route, APIRoute) and getattr(route, "path", None) == path:
            for dep in route.dependant.dependencies:
                if isinstance(dep, Dependant) and dep.call is not None:
                    call = dep.call

                    if name_contains in call.__qualname__:
                        app.dependency_overrides[call] = override


class TestAuthRoutes:
    """Tests for GitHub OAuth authentication routes."""

    async def test_github_oauth_authorize_redirect(
        self, async_client: AsyncClient
    ) -> None:
        """Ensure the GitHub OAuth authorize endpoint redirects or renders."""
        response = await async_client.get(f"{API_BASE}/auth/github/authorize")

        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_302_FOUND,
            status.HTTP_307_TEMPORARY_REDIRECT,
        )
        assert "github" in response.text.lower() or "oauth" in response.text.lower()

    async def test_github_oauth_authorize_embeds_return_to_in_state(
        self, async_client: AsyncClient
    ) -> None:
        return_to = "https://127.0.0.1:5173/simulations/test-run?tab=summary"

        response = await async_client.get(
            f"{API_BASE}/auth/github/authorize",
            params={"return_to": return_to},
        )

        assert response.status_code == status.HTTP_200_OK
        authorization_url = response.json()["authorization_url"]
        state = parse_qs(urlparse(authorization_url).query)["state"][0]
        state_data = decode_jwt(
            state,
            settings.github_state_secret_key,
            [STATE_TOKEN_AUDIENCE],
        )

        assert state_data["return_to"] == return_to

    async def test_github_oauth_callback_invalid_state(
        self, async_client: AsyncClient
    ) -> None:
        """Mock GitHub OAuth token + profile exchange (FastAPI-Users v14)."""
        with (
            patch.object(
                oauth,
                "_fetch_verified_e3sm_membership",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                oauth.GITHUB_OAUTH_CLIENT,
                "get_access_token",
                new=AsyncMock(return_value={"access_token": "fake_token"}),
            ),
            patch.object(
                oauth.GITHUB_OAUTH_CLIENT,
                "get_id_email",
                new=AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
            ),
        ):
            response = await async_client.get(
                f"{API_BASE}/auth/github/callback?code=fake&state=fake"
            )

        # Depending on cookie/JWT config, FastAPI-Users may redirect or just 400
        assert response.status_code in (200, 307, 400)

    async def test_github_oauth_callback_rejects_missing_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            AsyncMock(return_value=False),
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", None)),
        )

        with pytest.raises(HTTPException) as exc_info:
            await oauth.github_callback(
                Request({"type": "http", "headers": []}),
                access_token_state=({"access_token": "fake_token"}, "valid-state"),
                user_manager=SimpleNamespace(),
                strategy=object(),
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == oauth.ErrorCode.OAUTH_NOT_AVAILABLE_EMAIL

    async def test_github_oauth_callback_rejects_missing_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        membership_fetch = AsyncMock(return_value=False)
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            membership_fetch,
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )

        with pytest.raises(HTTPException) as exc_info:
            await oauth.github_callback(
                Request({"type": "http", "headers": []}),
                access_token_state=({"access_token": "fake_token"}, None),
                user_manager=SimpleNamespace(),
                strategy=object(),
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        membership_fetch.assert_not_awaited()

    async def test_github_oauth_callback_rejects_existing_user_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            AsyncMock(return_value=False),
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )
        monkeypatch.setattr(oauth, "decode_jwt", lambda *_args, **_kwargs: {})
        user_manager = SimpleNamespace(
            oauth_callback=AsyncMock(side_effect=UserAlreadyExists()),
            on_after_login=AsyncMock(),
        )

        with pytest.raises(HTTPException) as exc_info:
            await oauth.github_callback(
                Request({"type": "http", "headers": []}),
                access_token_state=({"access_token": "fake_token"}, "valid-state"),
                user_manager=user_manager,
                strategy=object(),
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == oauth.ErrorCode.OAUTH_USER_ALREADY_EXISTS

    async def test_github_oauth_callback_rejects_inactive_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        membership_fetch = AsyncMock(return_value=False)
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            membership_fetch,
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )
        monkeypatch.setattr(oauth, "decode_jwt", lambda *_args, **_kwargs: {})
        user_manager = SimpleNamespace(
            oauth_callback=AsyncMock(return_value=SimpleNamespace(is_active=False)),
            on_after_login=AsyncMock(),
        )

        with pytest.raises(HTTPException) as exc_info:
            await oauth.github_callback(
                Request({"type": "http", "headers": []}),
                access_token_state=({"access_token": "fake_token"}, "valid-state"),
                user_manager=user_manager,
                strategy=object(),
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == oauth.ErrorCode.LOGIN_BAD_CREDENTIALS
        membership_fetch.assert_not_awaited()

    async def test_github_oauth_callback_logs_in_and_redirects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        return_to = "https://127.0.0.1:5173/simulations/test-run?tab=summary"
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )
        monkeypatch.setattr(
            oauth, "decode_jwt", lambda *_args, **_kwargs: {"return_to": return_to}
        )
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_BACKEND,
            "login",
            AsyncMock(return_value=RedirectResponse("/", status_code=302)),
        )
        user = SimpleNamespace(is_active=True)
        user_manager = SimpleNamespace(
            oauth_callback=AsyncMock(return_value=user),
            refresh_github_org_membership=AsyncMock(return_value=user),
            on_after_login=AsyncMock(),
        )

        response = await oauth.github_callback(
            Request({"type": "http", "headers": []}),
            access_token_state=({"access_token": "fake_token"}, "valid-state"),
            user_manager=user_manager,
            strategy=object(),
        )

        assert response.status_code == status.HTTP_302_FOUND
        assert response.headers["location"].endswith(
            "auth/callback?return_to=https%3A%2F%2F127.0.0.1%3A5173%2Fsimulations%2Ftest-run%3Ftab%3Dsummary"
        )
        user_manager.refresh_github_org_membership.assert_awaited_once()
        user_manager.on_after_login.assert_awaited_once_with(user, ANY, response)

    async def test_github_oauth_callback_uses_refreshed_user_for_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )
        monkeypatch.setattr(oauth, "decode_jwt", lambda *_args, **_kwargs: {})
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            AsyncMock(return_value=True),
        )
        login_mock = AsyncMock(return_value=RedirectResponse("/", status_code=302))
        monkeypatch.setattr(oauth.GITHUB_OAUTH_BACKEND, "login", login_mock)
        original_user = SimpleNamespace(is_active=True, role=UserRole.USER)
        refreshed_user = SimpleNamespace(
            is_active=True,
            role=UserRole.USER,
            has_verified_e3sm_membership=True,
        )
        user_manager = SimpleNamespace(
            oauth_callback=AsyncMock(return_value=original_user),
            refresh_github_org_membership=AsyncMock(return_value=refreshed_user),
            on_after_login=AsyncMock(),
        )

        response = await oauth.github_callback(
            Request({"type": "http", "headers": []}),
            access_token_state=({"access_token": "fake_token"}, "valid-state"),
            user_manager=user_manager,
            strategy=object(),
        )

        user_manager.refresh_github_org_membership.assert_awaited_once_with(
            original_user,
            is_verified_member=True,
            checked_at=ANY,
        )
        login_mock.assert_awaited_once_with(ANY, refreshed_user)
        user_manager.on_after_login.assert_awaited_once_with(
            refreshed_user, ANY, response
        )

    async def test_fetch_verified_e3sm_membership_active_member(self) -> None:
        response = SimpleNamespace(status_code=200, json=lambda: {"state": "active"})
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = response

        with patch.object(oauth, "AsyncClient", return_value=client):
            result = await oauth._fetch_verified_e3sm_membership("token")

        assert result is True

    async def test_fetch_verified_e3sm_membership_non_member(self) -> None:
        missing_response = SimpleNamespace(status_code=404, json=lambda: {})
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = missing_response

        with patch.object(oauth, "AsyncClient", return_value=client):
            missing_result = await oauth._fetch_verified_e3sm_membership("token")

        assert missing_result is False

    async def test_fetch_verified_e3sm_membership_preserves_state_on_api_failure(
        self,
    ) -> None:
        failed_response = SimpleNamespace(status_code=503, json=lambda: {})
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = failed_response

        with patch.object(oauth, "AsyncClient", return_value=client):
            result = await oauth._fetch_verified_e3sm_membership("token")

        assert result is None

    async def test_fetch_verified_e3sm_membership_client_error_returns_none(
        self,
    ) -> None:
        failed_response = SimpleNamespace(status_code=403, json=lambda: {})
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = failed_response

        with patch.object(oauth, "AsyncClient", return_value=client):
            result = await oauth._fetch_verified_e3sm_membership("token")

        assert result is None

    async def test_fetch_verified_e3sm_membership_request_error_returns_none(
        self,
    ) -> None:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.side_effect = HTTPError("boom")

        with patch.object(oauth, "AsyncClient", return_value=client):
            result = await oauth._fetch_verified_e3sm_membership("token")

        assert result is None

    async def test_fetch_verified_e3sm_membership_invalid_json_returns_none(
        self,
    ) -> None:
        invalid_json_response = SimpleNamespace(
            status_code=200,
            json=lambda: (_ for _ in ()).throw(ValueError("bad json")),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = invalid_json_response

        with patch.object(oauth, "AsyncClient", return_value=client):
            result = await oauth._fetch_verified_e3sm_membership("token")

        assert result is None

    async def test_github_oauth_callback_does_not_downgrade_membership_on_api_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_CLIENT,
            "get_id_email",
            AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
        )
        monkeypatch.setattr(oauth, "decode_jwt", lambda *_args, **_kwargs: {})
        monkeypatch.setattr(
            oauth,
            "_fetch_verified_e3sm_membership",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            oauth.GITHUB_OAUTH_BACKEND,
            "login",
            AsyncMock(return_value=RedirectResponse("/", status_code=302)),
        )
        user = SimpleNamespace(is_active=True)
        user_manager = SimpleNamespace(
            oauth_callback=AsyncMock(return_value=user),
            refresh_github_org_membership=AsyncMock(return_value=user),
            on_after_login=AsyncMock(),
        )

        response = await oauth.github_callback(
            Request({"type": "http", "headers": []}),
            access_token_state=({"access_token": "fake_token"}, "valid-state"),
            user_manager=user_manager,
            strategy=object(),
        )

        assert response.status_code == status.HTTP_302_FOUND
        user_manager.refresh_github_org_membership.assert_not_awaited()


class TestLogOutRoute:
    """Tests for the logout route."""

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, async_client: AsyncClient) -> None:
        """Ensure the logout endpoint clears the cookie with correct attributes."""
        cookie_name = settings.cookie_name
        async_client.cookies.set(cookie_name, "fake_cookie_value")

        response = await async_client.post(f"{API_BASE}/auth/logout")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Successfully logged out"}

        set_cookie_header = response.headers.get("set-cookie", "")

        assert f"{cookie_name}=" in set_cookie_header
        assert "Max-Age=0" in set_cookie_header
        assert "Path=/" in set_cookie_header

        if settings.cookie_httponly:
            assert "HttpOnly" in set_cookie_header

        if settings.cookie_secure:
            assert "Secure" in set_cookie_header

        if settings.cookie_samesite:
            expected_samesite = f"samesite={settings.cookie_samesite.lower()}"
            assert expected_samesite in set_cookie_header.lower(), (
                f"Expected SameSite={settings.cookie_samesite}, "
                f"but got header: {set_cookie_header}"
            )

    @pytest.mark.asyncio
    async def test_logout_without_cookie(self, async_client: AsyncClient) -> None:
        """Ensure the logout endpoint works even if no cookie is set."""
        response = await async_client.post(f"{API_BASE}/auth/logout")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Successfully logged out"}


class TestUserRoutes:
    """Tests for user-related routes with mocked GitHub authentication."""

    async def test_users_me_requires_auth(self, async_client: AsyncClient) -> None:
        """Unauthenticated request to /users/me should return 401."""
        response = await async_client.get(f"{API_BASE}/users/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_users_me_authenticated(
        self, async_client: AsyncClient, normal_user
    ) -> None:
        """Override /users/me dependency with a serializable mock user."""

        def override_user():
            # Return something JSON-serializable that matches UserRead schema
            return {
                "id": normal_user["id"],
                "email": normal_user["email"],
                "is_active": True,
                "is_verified": True,
                "role": UserRole.USER.value,
                "has_verified_e3sm_membership": False,
            }

        override_dependency(f"{API_BASE}/users/me", "current_user", override_user)
        app.dependency_overrides[current_active_user] = override_user

        response = await async_client.get(f"{API_BASE}/users/me")
        assert response.status_code == 200, response.text

        data = response.json()
        assert set(data.keys()) >= {"id", "email", "is_active", "is_verified", "role"}
        assert data["email"] == normal_user["email"]
        assert data["can_edit_managed_content"] is False
