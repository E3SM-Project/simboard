"""Tests for token authentication utilities."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

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


@pytest.mark.usefixtures("db")
class TestValidateToken:
    """Tests for token validation (requires database)."""

    def test_validate_token_valid(self, db, normal_user_sync):
        """Test that a valid token returns the associated user."""
        # Create a test token
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        api_token = ApiToken(
            name="Test Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        # Validate token
        result = validate_token(raw_token, db)

        assert result is not None
        assert result.id == user.id
        assert result.email == user.email

    def test_validate_token_invalid(self, db):
        """Test that an invalid token returns None."""
        raw_token = "sbk_invalid_token_12345"

        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_revoked(self, db, normal_user_sync):
        """Test that a revoked token returns None."""
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        api_token = ApiToken(
            name="Revoked Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
            revoked=True,
        )
        db.add(api_token)
        db.commit()

        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_expired(self, db, normal_user_sync):
        """Test that an expired token returns None."""
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        api_token = ApiToken(
            name="Expired Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_not_expired(self, db, normal_user_sync):
        """Test that a non-expired token returns the user."""
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        api_token = ApiToken(
            name="Not Expired Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        result = validate_token(raw_token, db)

        assert result is not None
        assert result.id == user.id

    def test_validate_token_inactive_user(self, db, normal_user_sync):
        """Test that a token for an inactive user returns None."""
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        user.is_active = False
        api_token = ApiToken(
            name="Inactive User Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        result = validate_token(raw_token, db)

        assert result is None

    def test_validate_token_skip_expiration_check(self, db, normal_user_sync):
        """Test that expiration check can be skipped."""
        raw_token, token_hash = generate_token()

        user = db.query(User).filter(User.id == normal_user_sync["id"]).first()
        api_token = ApiToken(
            name="Expired Token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            revoked=False,
        )
        db.add(api_token)
        db.commit()

        result = validate_token(raw_token, db, check_expiration=False)

        assert result is not None
        assert result.id == user.id
