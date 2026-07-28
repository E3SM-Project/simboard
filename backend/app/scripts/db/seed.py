"""
SimBoard Development Seeder
-----------------------------
Seeds the database with case, execution, artifact, and external link data
from a JSON file. Safe to run only in non-production environments.

Usage:
    ENV=development python -m app.seed
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pydantic import AnyUrl, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 # required to register models with SQLAlchemy
from app.core.config import settings
from app.core.database import SessionLocal
from app.features.catalog.models import Artifact, Case, Execution, ExternalLink
from app.features.catalog.schemas import (
    ArtifactCreate,
    ExecutionCreate,
    ExternalLinkCreate,
)
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
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
DEV_HPC_USERNAME = "simboard-dev"


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

    total_executions = 0

    for case_entry in data:
        case_name = case_entry.get("caseName")
        if not case_name:
            raise ValueError(f"Missing 'caseName' in JSON case entry: {case_entry}")

        case_group = case_entry.get("caseGroup")
        executions_data = case_entry.get("executions", [])
        if not executions_data:
            raise ValueError(f"No executions for case '{case_name}'")

        case_machine = _resolve_seed_case_machine(db, executions_data, case_name)

        # Create the Case record
        case = Case(
            name=case_name,
            machine_id=case_machine.id,
            hpc_username=DEV_HPC_USERNAME,
            case_group=case_group,
        )
        db.add(case)
        db.flush()

        for execution_entry in executions_data:
            _ = _seed_execution(db, execution_entry, case, case_name, first_user_id)

            total_executions += 1

    db.commit()
    print(
        f"✅ Done! Inserted {len(data)} cases with "
        f"{total_executions} executions, artifacts, and links."
    )


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_date(value) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed is not None else None


def _resolve_seed_case_machine(
    db: Session, executions_data: list[dict], case_name: str
) -> Machine:
    first_execution = executions_data[0]
    machine_name = first_execution.get("machine", {}).get("name")
    if not machine_name:
        raise ValueError(
            f"Missing 'machine.name' in first execution entry for case '{case_name}'"
        )

    machine = db.query(Machine).filter(Machine.name == machine_name).one_or_none()
    if not machine:
        raise ValueError(
            f"No machine found in DB with name '{machine_name}' for case '{case_name}'"
        )

    for execution_entry in executions_data[1:]:
        current_machine_name = execution_entry.get("machine", {}).get("name")
        if not current_machine_name:
            raise ValueError(
                f"Missing 'machine.name' in execution entry for case '{case_name}'"
            )
        if current_machine_name != machine_name:
            raise ValueError(
                f"Seed case '{case_name}' mixes machines '{machine_name}' and "
                f"'{current_machine_name}', which is not allowed for normalized case identity"
            )

    return machine


def _seed_execution(
    db: Session, execution_entry: dict, case: Case, case_name: str, user_id
) -> Execution:
    """Create a single Execution, Ingestion, and related entities from seed data.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session
    execution_entry : dict
        Dictionary containing execution data from the legacy JSON contract
    case : Case
        The Case object this execution belongs to (must be added to session)
    case_name : str
        Name of the case (used for error messages)
    user_id : int
        ID of the user to set as createdBy/lastUpdatedBy for the execution and
        ingestion

    Returns
    -------
    Execution
        The created Execution object (not yet committed to DB)
    """
    machine_name = execution_entry.get("machine", {}).get("name")
    if not machine_name:
        raise ValueError(
            f"Missing 'machine.name' in execution entry for case '{case_name}'"
        )

    machine = db.query(Machine).filter(Machine.name == machine_name).one_or_none()
    if not machine:
        raise ValueError(
            f"No machine found in DB with name '{machine_name}' for case '{case_name}'"
        )

    seed_payload = {
        key: value
        for key, value in execution_entry.items()
        if key not in {"machine", "machineId", "hpcUsername"}
    }

    execution_in = ExecutionCreate(
        **{
            **seed_payload,
            "caseId": case.id,
            "simulationStartDate": _parse_date(
                execution_entry.get("simulationStartDate")
            ),
            "simulationEndDate": _parse_date(execution_entry.get("simulationEndDate")),
            "runStartDate": _parse_datetime(execution_entry.get("runStartDate")),
            "runEndDate": _parse_datetime(execution_entry.get("runEndDate")),
            "createdBy": user_id,
            "lastUpdatedBy": user_id,
            "artifacts": [
                ArtifactCreate(**a) for a in execution_entry.get("artifacts", [])
            ],
            "links": [
                ExternalLinkCreate(**link) for link in execution_entry.get("links", [])
            ],
        }
    )

    execution = Execution(
        **{
            **execution_in.model_dump(exclude={"artifacts", "links"}),
            "git_repository_url": str(execution_in.git_repository_url)
            if isinstance(execution_in.git_repository_url, HttpUrl)
            else execution_in.git_repository_url,
        }
    )

    execution_id = execution_entry.get("executionId")
    if not execution_id:
        raise ValueError(
            f"Missing 'executionId' in execution entry for case '{case_name}'"
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

    execution.ingestion_id = ingestion.id
    db.add(execution)
    db.flush()

    for a in execution_in.artifacts or []:
        db.add(
            Artifact(
                execution_id=execution.id,
                **{
                    **a.model_dump(),
                    "uri": str(a.uri) if isinstance(a.uri, AnyUrl) else a.uri,
                },
            )
        )

    for link in execution_in.links or []:
        db.add(
            ExternalLink(
                execution_id=execution.id,
                **{
                    **link.model_dump(),
                    "url": str(link.url) if isinstance(link.url, HttpUrl) else link.url,
                },
            )
        )

    return execution


if __name__ == "__main__":
    db = SessionLocal()
    mock_filepath = str(Path(__file__).resolve().parent / "catalog.json")

    try:
        create_dev_oauth_user(db)  # ✅ always ensure dummy user exists
        seed_from_json(db, mock_filepath)
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
