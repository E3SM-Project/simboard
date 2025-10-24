"""Rollback seeded data script from seed.py."""

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.artifact import Artifact
from app.db.models.link import ExternalLink
from app.db.models.simulation import Simulation
from app.db.session import AsyncSessionLocal


async def rollback_seed(db: AsyncSession):
    """Rollback all seeded data."""
    print("🔄 Rolling back seeded data...")
    try:
        await db.execute(delete(ExternalLink))
        await db.execute(delete(Artifact))
        await db.execute(delete(Simulation))
        await db.commit()

        print("✅ Rollback complete.")
    except Exception as e:
        await db.rollback()
        print(f"❌ Rollback failed: {e}")
        raise


async def main():
    async with AsyncSessionLocal() as db:
        await rollback_seed(db)


if __name__ == "__main__":
    asyncio.run(main())
