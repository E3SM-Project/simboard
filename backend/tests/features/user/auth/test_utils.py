"""Tests for authentication strategy utilities."""

from app.core.config import settings
from app.features.user.auth.oauth import GITHUB_OAUTH_BACKEND
from app.features.user.auth.token import JWT_BEARER_BACKEND
from app.features.user.auth.utils import BEARER_JWT_LIFETIME_SECONDS


def test_browser_login_jwt_uses_cookie_max_age(monkeypatch):
    """Browser login JWT lifetime matches the auth cookie lifetime."""
    monkeypatch.setattr(settings, "cookie_max_age", 1234)

    strategy = GITHUB_OAUTH_BACKEND.get_strategy()

    assert strategy.lifetime_seconds == 1234


def test_bearer_login_jwt_ignores_cookie_max_age(monkeypatch):
    """Password-login bearer JWTs keep their short fixed lifetime."""
    monkeypatch.setattr(settings, "cookie_max_age", 1234)

    strategy = JWT_BEARER_BACKEND.get_strategy()

    assert strategy.lifetime_seconds == BEARER_JWT_LIFETIME_SECONDS
