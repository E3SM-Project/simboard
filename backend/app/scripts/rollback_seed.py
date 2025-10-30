"""Rollback seeded data script from seed.py."""

from sqlalchemy.orm import Session

import app.models  # noqa: F401 # required to register models with SQLAlchemy
from app.core.database import SessionLocal
from app.features.simulation.models import Artifact, ExternalLink, Simulation


def rollback_seed(db: Session):
    """Rollback all seeded data."""
    print("🔄 Rolling back seeded data...")
    try:
        db.query(ExternalLink).delete()
        db.query(Artifact).delete()
        db.query(Simulation).delete()
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
