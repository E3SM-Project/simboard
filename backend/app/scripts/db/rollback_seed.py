"""Rollback seeded data script from seed.py."""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import app.models  # noqa: F401 # required to register models with SQLAlchemy
from app.core.config import settings
from app.core.database import SessionLocal
from app.features.ingestion.models import Ingestion
from app.features.simulation.models import (
    Artifact,
    Case,
    ExternalLink,
    Simulation,
)
from app.features.user.models import OAuthAccount, User

DEV_EMAIL = f"simboard-dev@{settings.domain}"
DEV_OAUTH_PROVIDER = "github"
SEED_SOURCE_PREFIX = "seed:%"


def rollback_seed(db: Session):
    """Rollback all seeded data."""
    print("🔄 Rolling back seeded data...")
    try:
        # Ingestions created by app/scripts/seed.py are marked as source_reference="seed:<name>"
        seed_ingestion_ids = (
            db.execute(
                select(Ingestion.id).where(
                    Ingestion.__table__.c.source_reference.like(SEED_SOURCE_PREFIX)
                )
            )
            .scalars()
            .all()
        )

        if seed_ingestion_ids:
            simulation_ids = (
                db.execute(
                    select(Simulation.id).where(
                        Simulation.__table__.c.ingestion_id.in_(seed_ingestion_ids)
                    )
                )
                .scalars()
                .all()
            )

            # Collect case_ids before deleting simulations
            case_ids: list[UUID] = []
            if simulation_ids:
                case_ids = list(
                    db.execute(
                        select(Simulation.__table__.c.case_id)
                        .where(Simulation.__table__.c.id.in_(simulation_ids))
                        .distinct()
                    )
                    .scalars()
                    .all()
                )

                db.execute(
                    delete(ExternalLink).where(
                        ExternalLink.__table__.c.simulation_id.in_(simulation_ids)
                    )
                )
                db.execute(
                    delete(Artifact).where(
                        Artifact.__table__.c.simulation_id.in_(simulation_ids)
                    )
                )

                # Clear reference_simulation_id on cases before deleting simulations
                if case_ids:
                    db.execute(
                        update(Case)
                        .where(Case.__table__.c.id.in_(case_ids))
                        .values(reference_simulation_id=None)
                    )

                db.execute(
                    delete(Simulation).where(
                        Simulation.__table__.c.id.in_(simulation_ids)
                    )
                )

            db.execute(
                delete(Ingestion).where(
                    Ingestion.__table__.c.id.in_(seed_ingestion_ids)
                )
            )

            # Delete cases that no longer have any simulations
            if case_ids:
                # Only delete cases that have no remaining simulations
                cases_with_sims = list(
                    db.execute(
                        select(Simulation.__table__.c.case_id)
                        .where(Simulation.__table__.c.case_id.in_(case_ids))
                        .distinct()
                    )
                    .scalars()
                    .all()
                )
                orphan_case_ids = set(case_ids) - set(cases_with_sims)
                if orphan_case_ids:
                    db.execute(
                        delete(Case).where(
                            Case.__table__.c.id.in_(list(orphan_case_ids))
                        )
                    )

        # Remove only the dummy OAuth account/user created by seed.py
        dev_user_id = db.execute(
            select(User.id).where(User.__table__.c.email == DEV_EMAIL)
        ).scalar_one_or_none()

        if dev_user_id:
            db.execute(
                delete(OAuthAccount).where(
                    OAuthAccount.__table__.c.user_id == dev_user_id,
                    OAuthAccount.__table__.c.oauth_name == DEV_OAUTH_PROVIDER,
                )
            )
            db.execute(delete(User).where(User.__table__.c.id == dev_user_id))

        db.commit()

        print("✅ Rollback complete.")
    except Exception as e:
        db.rollback()

        print(f"❌ Rollback failed: {e}")

        raise


if __name__ == "__main__":
    db = SessionLocal()

    rollback_seed(db)

    db.close()
