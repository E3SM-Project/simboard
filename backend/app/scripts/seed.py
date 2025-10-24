"""
EarthFrame Development Seeder
-----------------------------
Seeds the database with simulation, artifact, and external link data
from a JSON file. Safe to run only in non-production environments.

Usage:
    ENV=development python -m app.seed
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.artifact import Artifact
from app.db.models.link import ExternalLink
from app.db.models.machine import Machine
from app.db.models.simulation import Simulation
from app.db.session import AsyncSessionLocal
from app.schemas.artifact import ArtifactCreate
from app.schemas.link import ExternalLinkCreate
from app.schemas.simulation import SimulationCreate


async def main():
    async with AsyncSessionLocal() as db:
        try:
            await seed_from_json(db, mock_filepath)
        except Exception as e:
            print(f"❌ Seeding failed: {e}")
            await db.rollback()
            raise


# --------------------------------------------------------------------
# 🧱 Safety check
# --------------------------------------------------------------------
env = os.getenv("ENV", "development").lower()
if env == "production":
    print("❌ Refusing to seed database in production environment.")
    sys.exit(1)


async def seed_from_json(db: AsyncSession, json_path: str):
    print(f"🌱 Seeding database from {json_path}...")
    data = _load_json(json_path)

    # Clear dev data
    await db.execute(delete(ExternalLink))
    await db.execute(delete(Artifact))
    await db.execute(delete(Simulation))

    for entry in data:
        # --- 🔍 Match machine name to existing Machine.id ---
        machine_name = entry.get("machine", {}).get("name")
        if not machine_name:
            raise ValueError(
                f"Missing 'machine.name' in JSON entry: {entry.get('name')}"
            )

        result = await db.execute(select(Machine).filter(Machine.name == machine_name))
        machine = result.scalars().one_or_none()
        if not machine:
            raise ValueError(
                f"No machine found in DB with name '{machine_name}' "
                f"for simulation '{entry.get('name')}'"
            )

        # ✅ Step 1: Create Pydantic schema instance
        sim_in = SimulationCreate(
            **{
                **entry,
                "machineId": machine.id,  # ✅ use real ID from DB
                "simulationStartDate": _parse_datetime(
                    entry.get("simulationStartDate")
                ),
                "simulationEndDate": _parse_datetime(entry.get("simulationEndDate")),
                "runStartDate": _parse_datetime(entry.get("runStartDate")),
                "runEndDate": _parse_datetime(entry.get("runEndDate")),
                "createdAt": _parse_datetime(entry.get("createdAt")),
                "artifacts": [
                    ArtifactCreate(**artifact)
                    for artifact in entry.get("artifacts", [])
                ],
                "links": [
                    ExternalLinkCreate(**link) for link in entry.get("links", [])
                ],
            }
        )

        # ✅ Step 2: Convert to ORM
        sim = Simulation(**sim_in.model_dump(exclude={"artifacts", "links"}))
        db.add(sim)
        await db.flush()  # get generated sim.id

        # ✅ Step 3: Attach related data
        for a in sim_in.artifacts or []:
            db.add(Artifact(simulation_id=sim.id, **a.model_dump()))

        for link in sim_in.links or []:
            db.add(
                ExternalLink(
                    simulation_id=sim.id, **{**link.model_dump(), "url": str(link.url)}
                )
            )

    await db.commit()
    print(f"✅ Done! Inserted {len(data)} simulations with artifacts and links.")


def _load_json(path: str):
    """Load and parse a JSON seed file."""
    pathlib_path = Path(path)

    if not pathlib_path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    with open(pathlib_path, "r") as f:
        return json.load(f)


def _parse_datetime(value):
    """Safely parse various ISO8601 datetime formats."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


if __name__ == "__main__":
    mock_filepath = str(Path(__file__).resolve().parent / "simulations.json")
    asyncio.run(main())
