import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.ingest import ingest_archive
from app.features.ingestion.models import Ingestion
from app.features.ingestion.schemas import (
    IngestArchiveRequest,
    IngestArchiveResponse,
    IngestionCreate,
    IngestionStatus,
)
from app.features.simulation.models import Artifact, ExternalLink, Simulation
from app.features.simulation.schemas import SimulationCreate
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])


@router.post(
    "/from-path",
    response_model=IngestArchiveResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_from_path(
    payload: IngestArchiveRequest,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """Ingest an archive from a file system path and persist simulations."""
    try:
        simulations, created_count, duplicate_count, errors = ingest_archive(
            payload.archive_path, payload.output_dir, db
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    error_count = len(errors)

    if error_count == 0 and created_count > 0:
        status_value = IngestionStatus.SUCCESS.value
    elif error_count > 0 and created_count > 0:
        status_value = IngestionStatus.PARTIAL.value
    else:
        status_value = IngestionStatus.FAILED.value

    with transaction(db):
        _persist_simulations(simulations, db, user)

        ingestion_create = IngestionCreate(
            source_type="path",
            source_reference=str(payload.archive_path),
            triggered_by=user.id,
            status=status_value,
            created_count=created_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
            archive_sha256=None,
        )
        ingestion = Ingestion(
            **ingestion_create.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(ingestion)
        db.flush()

    return IngestArchiveResponse(
        created_count=created_count,
        duplicate_count=duplicate_count,
        simulations=simulations,
        errors=errors,
    )


@router.post(
    "/from-upload",
    response_model=IngestArchiveResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_from_upload(  # noqa: C901
    file: UploadFile = File(...),
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """Ingest an archive via file upload and persist simulations."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    filename = file.filename.lower()
    if not (
        filename.endswith(".zip")
        or filename.endswith(".tar.gz")
        or filename.endswith(".tgz")
    ):
        raise HTTPException(
            status_code=400, detail="File must be a .zip, .tar.gz, or .tgz archive"
        )

    # Optional: file size safety (20MB max)
    # TODO: Check to see what the max filesize should be based on expected use
    # cases and adjust as needed
    if hasattr(file, "size") and file.size and file.size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / file.filename
            sha256_hash = hashlib.sha256()

            # Save file and compute SHA256
            with open(archive_path, "wb") as out_file:
                while chunk := file.file.read(8192):
                    sha256_hash.update(chunk)
                    out_file.write(chunk)

            sha256_hex = sha256_hash.hexdigest()

            try:
                simulations, created_count, duplicate_count, errors = ingest_archive(
                    str(archive_path), tmpdir, db
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(exc)
                ) from exc
            except LookupError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
                ) from exc

            error_count = len(errors)

            if error_count == 0 and created_count > 0:
                status_value = IngestionStatus.SUCCESS.value
            elif error_count > 0 and created_count > 0:
                status_value = IngestionStatus.PARTIAL.value
            else:
                status_value = IngestionStatus.FAILED.value

            with transaction(db):
                _persist_simulations(simulations, db, user)

                ingestion_create = IngestionCreate(
                    source_type="upload",
                    source_reference=file.filename,
                    triggered_by=user.id,
                    status=status_value,
                    created_count=created_count,
                    duplicate_count=duplicate_count,
                    error_count=error_count,
                    archive_sha256=sha256_hex,
                )
                ingestion = Ingestion(
                    **ingestion_create.model_dump(),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(ingestion)
                db.flush()

            return IngestArchiveResponse(
                created_count=created_count,
                duplicate_count=duplicate_count,
                simulations=simulations,
                errors=errors,
            )
    finally:
        file.file.close()


def _persist_simulations(
    simulations: list[SimulationCreate],
    db: Session,
    user: User,
) -> None:
    """Persist simulation records with artifacts and links to the database."""
    now = datetime.now(timezone.utc)
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
                artifact_data = artifact.model_dump(by_alias=False, exclude_unset=True)
                artifact_data["uri"] = str(artifact.uri)
                sim.artifacts.append(Artifact(**artifact_data))

        if sim_create.links:
            for link in sim_create.links:
                link_data = link.model_dump(by_alias=False, exclude_unset=True)
                link_data["url"] = str(link.url)
                sim.links.append(ExternalLink(**link_data))

        db.add(sim)
        db.flush()
