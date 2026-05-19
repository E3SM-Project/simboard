import pytest
from fastapi import Response
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.features.user.auth.oauth import (
    CustomCookieTransport,
    _build_frontend_auth_redirect_url,
    _normalize_post_login_return_to,
)


@pytest.mark.asyncio
async def test_get_login_response_sets_cookie_and_redirects(monkeypatch):
    # Arrange
    token = "test-jwt-token"
    frontend_url = "https://frontend.example.com/auth/callback"
    cookie_name = "test_cookie"

    # Patch settings used in CustomCookieTransport
    monkeypatch.setattr(settings, "frontend_auth_redirect_url", frontend_url)
    monkeypatch.setattr(settings, "cookie_name", cookie_name)
    monkeypatch.setattr(settings, "cookie_max_age", 3600)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "cookie_httponly", True)
    monkeypatch.setattr(settings, "cookie_samesite", "lax")

    transport = CustomCookieTransport(
        cookie_name=cookie_name,
        cookie_max_age=3600,
        cookie_secure=False,
        cookie_httponly=True,
        cookie_samesite="lax",
    )

    # Act
    response: Response = await transport.get_login_response(token)

    # Assert
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == frontend_url

    # Check that the cookie is set in the response headers
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert cookie_name in set_cookie
    assert token in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Max-Age=3600" in set_cookie


@pytest.mark.asyncio
async def test_get_login_response_with_different_settings(monkeypatch):
    token = "another-token"
    frontend_url = "http://localhost:3000/after-login"
    cookie_name = "oauth_cookie"

    monkeypatch.setattr(settings, "frontend_auth_redirect_url", frontend_url)
    monkeypatch.setattr(settings, "cookie_name", cookie_name)
    monkeypatch.setattr(settings, "cookie_max_age", 100)
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "cookie_httponly", False)
    monkeypatch.setattr(settings, "cookie_samesite", "strict")

    transport = CustomCookieTransport(
        cookie_name=cookie_name,
        cookie_max_age=100,
        cookie_secure=True,
        cookie_httponly=False,
        cookie_samesite="strict",
    )

    response: Response = await transport.get_login_response(token)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == frontend_url
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert cookie_name in set_cookie
    assert token in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" not in set_cookie
    assert "Max-Age=100" in set_cookie
    assert "SameSite=strict" in set_cookie


def test_normalize_post_login_return_to_accepts_allowed_frontend_origin(monkeypatch):
    monkeypatch.setattr(
        settings,
        "frontend_origins",
        "https://127.0.0.1:5173,https://localhost:5173",
    )

    assert (
        _normalize_post_login_return_to(
            "https://127.0.0.1:5173/simulations/123?tab=1#rail"
        )
        == "https://127.0.0.1:5173/simulations/123?tab=1#rail"
    )


def test_normalize_post_login_return_to_rejects_unapproved_origin(monkeypatch):
    monkeypatch.setattr(settings, "frontend_origins", "https://127.0.0.1:5173")

    assert (
        _normalize_post_login_return_to("https://evil.example.com/simulations/123")
        is None
    )


def test_build_frontend_auth_redirect_url_appends_return_to(monkeypatch):
    monkeypatch.setattr(
        settings, "frontend_auth_redirect_url", "https://127.0.0.1:5173/auth/callback"
    )
    monkeypatch.setattr(settings, "frontend_origins", "https://127.0.0.1:5173")

    redirect_url = _build_frontend_auth_redirect_url(
        "https://127.0.0.1:5173/simulations/123?tab=summary"
    )

    assert (
        redirect_url
        == "https://127.0.0.1:5173/auth/callback?return_to=https%3A%2F%2F127.0.0.1%3A5173%2Fsimulations%2F123%3Ftab%3Dsummary"
    )
