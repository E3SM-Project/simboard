"""Tests for authentication strategy utilities."""

from app.core.config import settings
from app.features.user.auth.utils import get_jwt_strategy


def test_get_jwt_strategy_uses_cookie_max_age(monkeypatch):
    """JWT lifetime matches the auth cookie lifetime."""
    monkeypatch.setattr(settings, "cookie_max_age", 1234)

    strategy = get_jwt_strategy()

    assert strategy.lifetime_seconds == 1234
