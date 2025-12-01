"""
SimBoard Development Seeder
-----------------------------
Seeds the database with simulation, artifact, and external link data
from a JSON file. Safe to run only in non-production environments.

Usage:
    ENV=development python -m app.seed
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pydantic import AnyUrl, HttpUrl
from sqlalchemy.orm import Session

import app.models  # noqa: F401 # required to register models with SQLAlchemy
from app.core.database import SessionLocal
from app.features.machine.models import Machine
from app.features.simulation.models import Artifact, ExternalLink, Simulation
from app.features.simulation.schemas import (
    ArtifactCreate,
    ExternalLinkCreate,
    SimulationCreate,
)

# --------------------------------------------------------------------
# 🧱 Safety check
# --------------------------------------------------------------------
env = os.getenv("ENV", "development").lower()
if env == "production":
    print("❌ Refusing to seed database in production environment.")
    sys.exit(1)


def load_json(path: str):
    """Load and parse a JSON seed file."""
    path = Path(path)  # type: ignore

    if not path.exists():  # type: ignore
        raise FileNotFoundError(f"Seed file not found: {path}")

    with open(path, "r") as f:
        return json.load(f)


def seed_from_json(db: Session, json_path: str):
    print(f"🌱 Seeding database from {json_path}...")
    data = load_json(json_path)

    # Clear dev data
    db.query(ExternalLink).delete()
    db.query(Artifact).delete()
    db.query(Simulation).delete()

    for entry in data:
        # --- 🔍 Match machine name to existing Machine.id ---
        machine_name = entry.get("machine", {}).get("name")
        if not machine_name:
            raise ValueError(
                f"Missing 'machine.name' in JSON entry: {entry.get('name')}"
            )

        machine = db.query(Machine).filter(Machine.name == machine_name).one_or_none()
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
        sim = Simulation(
            **{
                **sim_in.model_dump(exclude={"artifacts", "links"}),
                "git_repository_url": str(sim_in.git_repository_url)
                if isinstance(sim_in.git_repository_url, HttpUrl)
                else sim_in.git_repository_url,
            }
        )
        db.add(sim)
        db.flush()  # get generated sim.id

        # ✅ Step 3: Attach related data
        for a in sim_in.artifacts or []:
            db.add(
                Artifact(
                    simulation_id=sim.id,
                    **{
                        **a.model_dump(),
                        "uri": str(a.uri) if isinstance(a.uri, AnyUrl) else a.uri,
                    },
                )
            )

        for link in sim_in.links or []:
            db.add(
                ExternalLink(
                    simulation_id=sim.id,
                    **{
                        **link.model_dump(),
                        "url": str(link.url)
                        if isinstance(link.url, HttpUrl)
                        else link.url,
                    },
                )
            )

    db.commit()
    print(f"✅ Done! Inserted {len(data)} simulations with artifacts and links.")


def _parse_datetime(value):
    """Safely parse various ISO8601 datetime formats."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


if __name__ == "__main__":
    db = SessionLocal()
    mock_filepath = str(Path(__file__).resolve().parent / "simulations.json")

    try:
        seed_from_json(db, mock_filepath)
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        db.rollback()

        raise
    finally:
        db.close()
