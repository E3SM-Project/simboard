"""Create a SERVICE_ACCOUNT user and generate an API token.

Usage:
    uv run python -m scripts.create_service_account <username> [--expires-in-days N]

Examples:
    uv run python -m scripts.create_service_account hpc-ingestion-bot
    uv run python -m scripts.create_service_account hpc-ingestion-bot --expires-in-days 365
"""

import argparse
import asyncio
import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database_async import AsyncSessionLocal
from app.features.user.models import ApiToken, User, UserRole


async def create_service_account(
    username: str, expires_in_days: int | None = None
) -> None:
    """Create a SERVICE_ACCOUNT user and associated API token.

    Parameters
    ----------
    username : str
        Username (used as email prefix and token name).
    expires_in_days : int | None
        Optional token expiration in days from now.
    """
    email = f"{username}@service.simboard.local"

    async with AsyncSessionLocal() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()

        if existing is not None:
            print(f"User '{email}' already exists (id={existing.id}). Exiting.")
            sys.exit(0)

        # Create the SERVICE_ACCOUNT user
        user = User(
            email=email,
            role=UserRole.SERVICE_ACCOUNT,
            is_active=True,
            is_superuser=False,
            is_verified=True,
            hashed_password=None,
        )
        session.add(user)
        await session.flush()

        # Generate API token
        raw_token = f"sbk_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        now = datetime.now(timezone.utc)
        expires_at = (
            now + timedelta(days=expires_in_days) if expires_in_days else None
        )

        api_token = ApiToken(
            name=f"{username}-token",
            token_hash=token_hash,
            user_id=user.id,
            created_at=now,
            expires_at=expires_at,
            revoked=False,
        )
        session.add(api_token)

        # Commit atomically
        await session.commit()

        print(f"Created SERVICE_ACCOUNT user: {email} (id={user.id})")
        print(f"Created API token: {api_token.name} (id={api_token.id})")
        if expires_at:
            print(f"Token expires at: {expires_at.isoformat()}")
        print()
        print(f"API Token: {raw_token}")
        print()
        print("WARNING: Store securely. This token will not be shown again.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a SERVICE_ACCOUNT user and generate an API token."
    )
    parser.add_argument("username", help="Username for the service account")
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="Token expiration in days (default: no expiration)",
    )

    args = parser.parse_args()
    asyncio.run(create_service_account(args.username, args.expires_in_days))


if __name__ == "__main__":
    main()
