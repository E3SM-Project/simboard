"""
SimBoard Development Seeder
-----------------------------
Seeds the database with case, simulation, artifact, and external link data
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
from app.core.config import settings
from app.core.database import SessionLocal
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation
from app.features.simulation.schemas import (
    ArtifactCreate,
    ExternalLinkCreate,
    SimulationCreate,
)
from app.features.user.models import OAuthAccount, User
from app.scripts.db.rollback_seed import rollback_seed

# --------------------------------------------------------------------
# 🧱 Safety check
# --------------------------------------------------------------------
env = os.getenv("ENV", "development").lower()
if env == "production":
    print("❌ Refusing to seed database in production environment.")
    sys.exit(1)


DEV_EMAIL = f"simboard-dev@{settings.domain}"
DEV_OAUTH_PROVIDER = "github"


# --------------------------------------------------------------------
# 🧑‍💻 Create a dummy OAuth user (GitHub-style)
# --------------------------------------------------------------------
def create_dev_oauth_user(db: Session):
    """Ensure a dummy OAuth user + OAuthAccount exist for development."""
    dev_email = DEV_EMAIL
    provider = DEV_OAUTH_PROVIDER

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

        # OAuth doesn't exist, create it
        oauth = OAuthAccount(
            user_id=user.id,
            oauth_name=provider,
            account_id="123456",
            account_email=dev_email,
            access_token="gho_dummy_token_12345",
            refresh_token="dummy_refresh_token_12345",
            expires_at=int(
                (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
            ),
        )
        db.add(oauth)
        db.commit()
        print(f"✅ Created OAuth account for existing user: {user.email} ({provider})")

        return user

    # 2. Create the user (no password needed for OAuth users)
    user = User(
        email=dev_email,
        role="user",
        hashed_password="",  # OAuth users don’t have local passwords
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(user)
    db.flush()  # generate user.id
    print(f"✅ Created dummy user: {user.email}")

    # 3. Create the linked OAuthAccount
    oauth = OAuthAccount(
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

    # Clear dev data using rollback_seed
    rollback_seed(db)

    # ✅ Ensure at least one user exists
    first_user = db.query(User).order_by(User.id.asc()).first()
    if not first_user:
        first_user = create_dev_oauth_user(db)
        db.refresh(first_user)

    first_user_id = first_user.id

    total_sims = 0

    for case_entry in data:
        case_name = case_entry.get("caseName")
        if not case_name:
            raise ValueError(f"Missing 'caseName' in JSON case entry: {case_entry}")

        case_group = case_entry.get("caseGroup")
        simulations_data = case_entry.get("simulations", [])
        if not simulations_data:
            raise ValueError(f"No simulations for case '{case_name}'")

        # Create the Case record
        case = Case(name=case_name, case_group=case_group)
        db.add(case)
        db.flush()

        first_sim = None

        for sim_entry in simulations_data:
            sim = _seed_simulation(db, sim_entry, case, case_name, first_user_id)

            if first_sim is None:
                first_sim = sim

            total_sims += 1

        # Set the first simulation as the reference for this case
        if first_sim is not None:
            if first_sim.id is not None:
                case.reference_simulation_id = first_sim.id
            db.flush()

    db.commit()
    print(
        f"✅ Done! Inserted {len(data)} cases with "
        f"{total_sims} simulations, artifacts, and links."
    )


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _seed_simulation(
    db: Session, sim_entry: dict, case: Case, case_name: str, user_id
) -> Simulation:
    """Create a single Simulation, Ingestion, and related entities from seed data.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session
    sim_entry : dict
        Dictionary containing simulation data from JSON
    case : Case
        The Case object this simulation belongs to (must be added to session)
    case_name : str
        Name of the case (used for error messages)
    user_id : int
        ID of the user to set as createdBy/lastUpdatedBy for the simulation and
        ingestion

    Returns
    -------
    Simulation
        The created Simulation object (not yet committed to DB)
    """
    machine_name = sim_entry.get("machine", {}).get("name")
    if not machine_name:
        raise ValueError(
            f"Missing 'machine.name' in simulation entry for case '{case_name}'"
        )

    machine = db.query(Machine).filter(Machine.name == machine_name).one_or_none()
    if not machine:
        raise ValueError(
            f"No machine found in DB with name '{machine_name}' for case '{case_name}'"
        )

    sim_in = SimulationCreate(
        **{
            **sim_entry,
            "caseId": case.id,
            "machineId": machine.id,
            "simulationStartDate": _parse_datetime(
                sim_entry.get("simulationStartDate")
            ),
            "simulationEndDate": _parse_datetime(sim_entry.get("simulationEndDate")),
            "runStartDate": _parse_datetime(sim_entry.get("runStartDate")),
            "runEndDate": _parse_datetime(sim_entry.get("runEndDate")),
            "createdBy": user_id,
            "lastUpdatedBy": user_id,
            "artifacts": [ArtifactCreate(**a) for a in sim_entry.get("artifacts", [])],
            "links": [
                ExternalLinkCreate(**link) for link in sim_entry.get("links", [])
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

    execution_id = sim_entry.get("executionId")
    if not execution_id:
        raise ValueError(
            f"Missing 'executionId' in simulation entry for case '{case_name}'"
        )

    ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference=f"seed:{case_name}/{execution_id}",
        machine_id=machine.id,
        triggered_by=user_id,
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        archive_sha256=None,
    )
    db.add(ingestion)
    db.flush()

    sim.ingestion_id = ingestion.id
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
                    "url": str(link.url) if isinstance(link.url, HttpUrl) else link.url,
                },
            )
        )

    return sim


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
