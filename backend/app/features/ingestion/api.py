from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.ingest import ingest_archive
from app.features.ingestion.schemas import IngestArchiveRequest, IngestArchiveResponse
from app.features.simulation.models import Artifact, ExternalLink, Simulation
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post(
    "/ingest-from-pathI",
    response_model=IngestArchiveResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_archive_to_db(
    payload: IngestArchiveRequest,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """Ingest an archive and persist simulations to the database."""
    try:
        simulations, created_count, duplicate_count, errors = ingest_archive(
            payload.archive_path, payload.output_dir, db
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    now = datetime.now(timezone.utc)

    with transaction(db):
        for sim_create in simulations:
            sim = Simulation(
                **sim_create.model_dump(
                    by_alias=False,
                    exclude={"artifacts", "links"},
                    exclude_unset=True,
                ),
                created_by=user.id,
                last_updated_by=user.id,
                created_at=now,
                updated_at=now,
            )

            if sim_create.artifacts:
                for artifact in sim_create.artifacts:
                    artifact_data = artifact.model_dump(
                        by_alias=False, exclude_unset=True
                    )
                    artifact_data["uri"] = str(artifact.uri)
                    sim.artifacts.append(Artifact(**artifact_data))

            if sim_create.links:
                for link in sim_create.links:
                    link_data = link.model_dump(by_alias=False, exclude_unset=True)
                    link_data["url"] = str(link.url)
                    sim.links.append(ExternalLink(**link_data))

            db.add(sim)
            db.flush()

    response = IngestArchiveResponse(
        created_count=created_count,
        duplicate_count=duplicate_count,
        simulations=simulations,
        errors=errors,
    )

    return response
