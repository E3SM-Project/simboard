import asyncio
import getpass

from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from app.core.config import settings
from app.core.database_async import AsyncSessionLocal
from app.features.user.models import User, UserRole


async def create_admin():
    default_email = f"admin@{settings.domain}"
    email = input(f"Admin email [{default_email}]: ").strip() or default_email

    password = getpass.getpass("Enter admin password: ")
    confirm = getpass.getpass("Confirm admin password: ")

    if password != confirm:
        raise RuntimeError("Passwords do not match.")

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash(password)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin already exists.")
            return

        user = User(
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True,
            is_verified=True,
            role=UserRole.ADMIN,
        )

        session.add(user)
        await session.commit()

        print("Admin created:", email)


if __name__ == "__main__":
    asyncio.run(create_admin())
