"""Token authentication utilities for API token management."""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from sqlalchemy.orm import Session

from app.features.user.auth.utils import get_jwt_strategy
from app.features.user.models import ApiToken, User, UserRole

# Bearer transport for JWT login (returns token as JSON).
BEARER_TRANSPORT = BearerTransport(tokenUrl="auth/jwt/login")

# JWT auth backend for username/password login via Bearer token.
JWT_BEARER_BACKEND: AuthenticationBackend = AuthenticationBackend(
    name="jwt", transport=BEARER_TRANSPORT, get_strategy=get_jwt_strategy
)


def generate_token() -> tuple[str, str]:
    """
    Generate a secure API token and its hash.

    Returns a tuple of (raw_token, token_hash).
    The raw token should be returned to the user once at creation.
    The token_hash should be stored in the database.

    The raw token is prefixed with 'sbk_' for operational clarity.

    Returns
    -------
    tuple[str, str]
        A tuple containing (raw_token, token_hash)
    """
    # Generate at least 32 bytes of entropy
    raw_token_b64 = secrets.token_urlsafe(32)
    raw_token = f"sbk_{raw_token_b64}"

    # SHA256 hash the token for storage
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    return raw_token, token_hash


def validate_token(
    raw_token: str, db: Session, *, check_expiration: bool = True
) -> Optional[User]:
    """
    Validate an API token and return the associated user.

    This function:
    1. Computes SHA256 hash of the provided token
    2. Looks up the token in the database by hash (indexed)
    3. Checks if token is revoked
    4. Optionally checks if token is expired
    5. Returns the associated user if valid, None otherwise

    Parameters
    ----------
    raw_token : str
        The raw API token to validate
    db : Session
        Database session
    check_expiration : bool, optional
        Whether to check token expiration, by default True

    Returns
    -------
    Optional[User]
        The user associated with the token if valid, None otherwise

    Security Notes
    --------------
    - Tokens are stored as SHA256 hashes, never in plaintext.
    - The DB lookup uses an indexed hash column, so query time is
      consistent regardless of whether the token exists (no
      timing side-channel for token discovery).
    - Subsequent checks (revoked, expired) only execute after a
      matching hash is found, so they reveal status of an already-
      known token — not useful for discovering valid tokens.
    - Never logs raw tokens.
    """
    # Compute hash of provided token
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    # Look up token by hash (indexed column — consistent query time).
    token = db.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()

    if not token:
        return None

    # Check if token is revoked
    if token.revoked:
        return None

    # Check expiration if requested
    if check_expiration and token.expires_at:
        if datetime.now(timezone.utc) > token.expires_at:
            return None

    # Load and return associated user
    user = db.query(User).filter(User.id == token.user_id).first()

    if not user or not user.is_active:
        return None

    # Only SERVICE_ACCOUNT users may authenticate via API tokens
    if user.role != UserRole.SERVICE_ACCOUNT:
        return None

    return user


def hash_token(raw_token: str) -> str:
    """
    Compute SHA256 hash of a token.

    Parameters
    ----------
    raw_token : str
        The raw token to hash

    Returns
    -------
    str
        Hexadecimal digest of the SHA256 hash
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()
