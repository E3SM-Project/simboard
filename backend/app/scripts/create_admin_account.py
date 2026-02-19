import asyncio
import getpass

from fastapi_users.password import PasswordHelper

from app.core.config import settings
from app.core.database_async import AsyncSessionLocal
from app.features.user.models import User, UserRole

ADMIN_EMAIL = f"admin@{settings.domain}"


async def create_admin():
    password = getpass.getpass("Enter admin password: ")
    confirm = getpass.getpass("Confirm admin password: ")

    if password != confirm:
        raise RuntimeError("Passwords do not match.")

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash(password)

    async with AsyncSessionLocal() as session:
        # Check if exists
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        existing = result.first()

        if existing:
            print("Admin already exists.")
            return

        user = User(
            email=ADMIN_EMAIL,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True,
            is_verified=True,
            role=UserRole.ADMIN,
        )

        session.add(user)
        await session.commit()

        print("Admin created:", ADMIN_EMAIL)


if __name__ == "__main__":
    asyncio.run(create_admin())
