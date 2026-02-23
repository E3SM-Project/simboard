"""Tests for token authentication utilities."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.features.user.models import ApiToken, User, UserRole
from app.features.user.token_auth import generate_token, hash_token, validate_token


class TestGenerateToken:
    """Tests for token generation."""

    def test_generate_token_returns_tuple(self):
        """Test that generate_token returns a tuple of (raw_token, token_hash)."""
        raw_token, token_hash = generate_token()

        assert isinstance(raw_token, str)
        assert isinstance(token_hash, str)

    def test_generate_token_has_prefix(self):
        """Test that generated tokens have the 'sbk_' prefix."""
        raw_token, _ = generate_token()

        assert raw_token.startswith("sbk_")

    def test_generate_token_hash_matches(self):
        """Test that the hash matches the raw token."""
        raw_token, token_hash = generate_token()

        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert token_hash == expected_hash

    def test_generate_token_unique(self):
        """Test that each call generates a unique token."""
        token1, hash1 = generate_token()
        token2, hash2 = generate_token()

        assert token1 != token2
        assert hash1 != hash2


class TestHashToken:
    """Tests for token hashing."""

    def test_hash_token_sha256(self):
        """Test that hash_token produces correct SHA256 hash."""
        raw_token = "sbk_test_token_12345"
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        result = hash_token(raw_token)

        assert result == expected_hash

    def test_hash_token_deterministic(self):
        """Test that hashing is deterministic."""
        raw_token = "sbk_test_token_67890"

        hash1 = hash_token(raw_token)
        hash2 = hash_token(raw_token)

        assert hash1 == hash2


def _mock_db(token=None, user=None):
    """Create a mock DB session that returns the given token and user."""
    db = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()
        mock_filter = MagicMock()
        if model is ApiToken:
            mock_filter.first.return_value = token
        elif model is User:
            mock_filter.first.return_value = user
        else:
            mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        return mock_query

    db.query.side_effect = query_side_effect
    return db


def _make_service_user(is_active=True, role=UserRole.SERVICE_ACCOUNT):
    """Create a User model instance for tests."""
    user = User(
        id=uuid.uuid4(),
        email="service@example.com",
        is_active=is_active,
        is_verified=True,
        role=role,
    )
    return user


class TestValidateToken:
    """Tests for token validation using mocked database."""

    def test_validate_token_valid(self):
        """Test that a valid token returns the associated user."""
        user = _make_service_user()
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.user_id = user.id
        token.revoked = False
        token.expires_at = None

        db = _mock_db(token=token, user=user)
        result = validate_token(raw_token, db)

        assert result is not None
        assert result.id == user.id
        assert result.email == user.email

    def test_validate_token_invalid(self):
        """Test that an invalid token returns None."""
        db = _mock_db(token=None)
        result = validate_token("sbk_invalid_token_12345", db)

        assert result is None

    def test_validate_token_revoked(self):
        """Test that a revoked token returns None."""
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.revoked = True

        db = _mock_db(token=token)
        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_expired(self):
        """Test that an expired token returns None."""
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.revoked = False
        token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        db = _mock_db(token=token)
        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_not_expired(self):
        """Test that a non-expired token returns the user."""
        user = _make_service_user()
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.user_id = user.id
        token.revoked = False
        token.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        db = _mock_db(token=token, user=user)
        result = validate_token(raw_token, db)

        assert result is not None
        assert result.id == user.id

    def test_validate_token_inactive_user(self):
        """Test that a token for an inactive user returns None."""
        user = _make_service_user(is_active=False)
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.user_id = user.id
        token.revoked = False
        token.expires_at = None

        db = _mock_db(token=token, user=user)
        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_non_service_account_rejected(self):
        """Test that tokens for non-SERVICE_ACCOUNT users are rejected."""
        user = _make_service_user(role=UserRole.USER)
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.user_id = user.id
        token.revoked = False
        token.expires_at = None

        db = _mock_db(token=token, user=user)
        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_skip_expiration_check(self):
        """Test that expiration check can be skipped."""
        user = _make_service_user()
        raw_token, token_hash = generate_token()

        token = MagicMock(spec=ApiToken)
        token.token_hash = token_hash
        token.user_id = user.id
        token.revoked = False
        token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        db = _mock_db(token=token, user=user)
        result = validate_token(raw_token, db, check_expiration=False)

        assert result is not None
        assert result.id == user.id
