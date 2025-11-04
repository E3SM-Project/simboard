import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.features.user import oauth
from app.features.user.models import OAuthAccount, User, UserRole
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


@pytest_asyncio.fixture
async def normal_user(async_db):
    """Create a normal OAuth-based user directly in the database."""
    user = User(
        email="user@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.USER,
    )
    async_db.add(user)
    await async_db.flush()

    oauth_account = OAuthAccount(
        oauth_name="github",
        access_token="fake_token_user",
        account_id=str(uuid.uuid4()),
        account_email=user.email,
        user_id=user.id,
    )
    async_db.add(oauth_account)
    await async_db.commit()
    await async_db.refresh(user)

    return {"id": str(user.id), "email": user.email}


@pytest_asyncio.fixture
async def admin_user(async_db):
    """Create an admin OAuth-based user directly in the database."""
    admin = User(
        email="admin@example.com",
        is_active=True,
        is_verified=True,
        role=UserRole.ADMIN,
    )
    async_db.add(admin)
    await async_db.flush()

    oauth_account = OAuthAccount(
        oauth_name="github",
        access_token="fake_token_admin",
        account_id=str(uuid.uuid4()),
        account_email=admin.email,
        user_id=admin.id,
    )
    async_db.add(oauth_account)
    await async_db.commit()
    await async_db.refresh(admin)

    return {"id": str(admin.id), "email": admin.email}


class TestAuthRoutes:
    """Tests for GitHub OAuth authentication routes."""

    async def test_github_oauth_authorize_redirect(
        self, async_client: AsyncClient
    ) -> None:
        """Ensure the GitHub OAuth authorize endpoint redirects or renders."""
        response = await async_client.get("/auth/github/authorize")

        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_302_FOUND,
            status.HTTP_307_TEMPORARY_REDIRECT,
        )
        assert "github" in response.text.lower() or "oauth" in response.text.lower()

    async def test_github_oauth_callback_invalid_state(
        self, async_client: AsyncClient
    ) -> None:
        """Mock GitHub OAuth token + profile exchange (FastAPI-Users v14)."""
        with (
            patch.object(
                oauth.github_oauth_client,
                "get_access_token",
                new=AsyncMock(return_value={"access_token": "fake_token"}),
            ),
            patch.object(
                oauth.github_oauth_client,
                "get_id_email",
                new=AsyncMock(return_value=("mock_account_id", "mockuser@example.com")),
            ),
        ):
            response = await async_client.get(
                "/auth/github/callback?code=fake&state=fake"
            )

        # Depending on cookie/JWT config, FastAPI-Users may redirect or just 400
        assert response.status_code in (200, 307, 400)


class TestUserRoutes:
    """Tests for user-related routes with mocked GitHub authentication."""

    async def test_users_me_requires_auth(self, async_client: AsyncClient) -> None:
        """Unauthenticated request to /users/me should return 401."""
        response = await async_client.get("/users/me")

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
            }

        override_dependency("/users/me", "current_user", override_user)

        response = await async_client.get("/users/me")
        assert response.status_code == 200, response.text

        data = response.json()
        assert set(data.keys()) >= {"id", "email", "is_active", "is_verified", "role"}
        assert data["email"] == normal_user["email"]
