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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import AnyUrl, HttpUrl
from sqlalchemy import select
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
from app.features.user.models import OAuthAccount, User

# --------------------------------------------------------------------
# 🧱 Safety check
# --------------------------------------------------------------------
env = os.getenv("ENV", "development").lower()
if env == "production":
    print("❌ Refusing to seed database in production environment.")
    sys.exit(1)


# --------------------------------------------------------------------
# 🧑‍💻 Create a dummy OAuth user (GitHub-style)
# --------------------------------------------------------------------
def create_dev_oauth_user(db: Session):
    """Ensure a dummy OAuth user + OAuthAccount exist for development."""
    dev_email = "simboard-dev@example.com"
    provider = "github"

    # 1. Check if the user already exists
    stmt = select(User).where(User.email == dev_email)
    user = db.execute(stmt).scalars().one_or_none()

    if user is not None:
        print(f"🔑 Dev user already exists: {user.email}")

        # Check if an OAuthAccount already exists for this user/provider
        stmt = (
            select(OAuthAccount)
            .where(OAuthAccount.user_id == user.id)
            .where(OAuthAccount.oauth_name == provider)
        )
        oauth_exists = db.execute(stmt).scalars().one_or_none()

        if oauth_exists:
            print(f"🔑 OAuth account already exists for {provider} → {user.email}")
            return user

        return user

    # 2. Create the user (no password needed for OAuth users)
    user = User(
        email=dev_email,
        role="admin",
        hashed_password="",  # OAuth users don’t have local passwords
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    db.add(user)
    db.flush()  # generate user.id
    print(f"✅ Created dummy user: {user.email}")

    # 3. Create the linked OAuthAccount
    oauth: OAuthAccount = OAuthAccount(
        user_id=user.id,
        oauth_name=provider,
        account_id="123456",  # fake GitHub user ID
        account_email=dev_email,
        access_token="gho_dummy_token_12345",
        refresh_token="dummy_refresh_token_12345",
        expires_at=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    )
    db.add(oauth)
    db.commit()

    print(f"✅ Created dev user + OAuth account: {user.email} ({provider})")

    return user


# --------------------------------------------------------------------
# 🌱 Main seeding logic
# --------------------------------------------------------------------
def load_json(path: str) -> dict:
    """Load and parse a JSON seed file."""
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Seed file not found: {path_obj}")
    with open(path_obj, "r") as f:
        return json.load(f)


def seed_from_json(db: Session, json_path: str):
    print(f"🌱 Seeding database from {json_path}...")
    data = load_json(json_path)

    # Clear dev data
    db.query(ExternalLink).delete()
    db.query(Artifact).delete()
    db.query(Simulation).delete()

    for entry in data:
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

        # ✅ Ensure at least one user exists
        first_user = db.query(User).order_by(User.id.asc()).first()
        if not first_user:
            first_user = create_dev_oauth_user(db)
            db.refresh(first_user)

        first_user_id = first_user.id

        sim_in = SimulationCreate(
            **{
                **entry,
                "machineId": machine.id,
                "simulationStartDate": _parse_datetime(
                    entry.get("simulationStartDate")
                ),
                "simulationEndDate": _parse_datetime(entry.get("simulationEndDate")),
                "runStartDate": _parse_datetime(entry.get("runStartDate")),
                "runEndDate": _parse_datetime(entry.get("runEndDate")),
                "createdAt": _parse_datetime(entry.get("createdAt")),
                "createdBy": first_user_id,
                "updatedBy": first_user_id,
                "lastUpdatedBy": first_user_id,
                "artifacts": [ArtifactCreate(**a) for a in entry.get("artifacts", [])],
                "links": [
                    ExternalLinkCreate(**link) for link in entry.get("links", [])
                ],
            }
        )

        sim = Simulation(
            **{
                **sim_in.model_dump(exclude={"artifacts", "links"}),
                "git_repository_url": str(sim_in.git_repository_url)
                if isinstance(sim_in.git_repository_url, HttpUrl)
                else sim_in.git_repository_url,
            }
        )
        db.add(sim)
        db.flush()

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
        create_dev_oauth_user(db)  # ✅ always ensure dummy user exists
        seed_from_json(db, mock_filepath)
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
