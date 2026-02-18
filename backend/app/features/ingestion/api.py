import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.ingest import ingest_archive
from app.features.ingestion.models import Ingestion, IngestionSourceType
from app.features.ingestion.schemas import (
    IngestFromPathRequest,
    IngestionCreate,
    IngestionResponse,
    IngestionStatus,
)
from app.features.machine.models import Machine
from app.features.simulation.models import Artifact, ExternalLink, Simulation
from app.features.simulation.schemas import SimulationCreate
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])


@router.post(
    "/from-path",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Ingestion successful, simulations created."},
        400: {"description": "Invalid input or archive file."},
        403: {"description": "Forbidden: only administrators can ingest from paths."},
        404: {"description": "Machine not found."},
        409: {"description": "Conflict: ingestion error."},
        500: {"description": "Internal server error."},
    },
)
def ingest_from_path(
    payload: IngestFromPathRequest,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """
    Ingest an archive from a filesystem path and persist simulations.

    NOTE:
    Arbitrary filesystem paths are currently permitted to support HPC
    ingestion workflows (e.g., NERSC). This endpoint is restricted to
    administrators.

    TODO:
    Consider enforcing that archive_path must reside within a configured
    base directory (e.g., a designated HPC storage or ingestion directory)
    before exposing this endpoint beyond a trusted environment.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators may ingest from filesystem paths.",
        )

    machine = db.query(Machine).filter(Machine.name == payload.machine_name).first()

    if not machine:
        raise HTTPException(
            status_code=404, detail=f"Machine '{payload.machine_name}' not found."
        )

    archive_path = Path(payload.archive_path)
    _validate_archive_path(archive_path)
    archive_sha256 = _compute_archive_sha256(archive_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        simulations, created_count, duplicate_count, errors = _run_ingest_archive(
            archive_path=str(archive_path),
            output_dir=tmpdir,
            db=db,
        )

    return _persist_and_respond_to_ingestion(
        simulations=simulations,
        created_count=created_count,
        duplicate_count=duplicate_count,
        errors=errors,
        source_type=IngestionSourceType.HPC_PATH,
        source_reference=str(archive_path),
        machine_id=machine.id,
        user=user,
        archive_sha256=archive_sha256,
        db=db,
    )


@router.post(
    "/from-upload",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Ingestion successful, simulations created."},
        400: {"description": "Invalid input or upload file."},
        404: {"description": "Machine not found."},
        409: {"description": "Conflict: ingestion error."},
        413: {"description": "File too large."},
        500: {"description": "Internal server error."},
    },
)
def ingest_from_upload(  # noqa: C901
    file: UploadFile = File(...),
    machine_name: str = Form(...),
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """Ingest an archive via file upload and persist simulations."""
    machine = db.query(Machine).filter(Machine.name == machine_name).first()

    if not machine:
        raise HTTPException(
            status_code=404, detail=f"Machine '{machine_name}' not found."
        )

    _validate_upload_file(file)
    filename = file.filename
    if filename is None:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / filename
            sha256_hex = _save_uploaded_file_and_hash(file, archive_path)

            simulations, created_count, duplicate_count, errors = _run_ingest_archive(
                archive_path=str(archive_path),
                output_dir=tmpdir,
                db=db,
            )

            return _persist_and_respond_to_ingestion(
                simulations=simulations,
                created_count=created_count,
                duplicate_count=duplicate_count,
                errors=errors,
                source_type=IngestionSourceType.HPC_UPLOAD,
                source_reference=filename,
                machine_id=machine.id,
                user=user,
                archive_sha256=sha256_hex,
                db=db,
            )
    finally:
        file.file.close()


def _validate_archive_path(archive_path: Path) -> None:
    if not archive_path.exists() or not archive_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive path '{archive_path}' does not exist or is not a file.",
        )


def _compute_archive_sha256(archive_path: Path) -> str:
    sha256_hash = hashlib.sha256()

    try:
        with archive_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute SHA256 for '{archive_path}': {exc}",
        ) from exc


def _validate_upload_file(file: UploadFile) -> None:
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

    if hasattr(file, "size") and file.size and file.size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")


def _save_uploaded_file_and_hash(
    file: UploadFile,
    archive_path: Path,
) -> str:
    sha256_hash = hashlib.sha256()

    with archive_path.open("wb") as out_file:
        for chunk in iter(lambda: file.file.read(8192), b""):
            out_file.write(chunk)
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def _run_ingest_archive(
    archive_path: str, output_dir: str, db: Session
) -> tuple[list[SimulationCreate], int, int, list[dict[str, str]]]:
    try:
        return ingest_archive(archive_path=archive_path, output_dir=output_dir, db=db)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


def _resolve_ingestion_status(created_count: int, error_count: int) -> str:
    if error_count == 0 and created_count > 0:
        return IngestionStatus.SUCCESS.value

    if error_count > 0 and created_count > 0:
        return IngestionStatus.PARTIAL.value

    return IngestionStatus.FAILED.value


def _persist_simulations(
    simulations: list[SimulationCreate],
    db: Session,
    user: User,
) -> None:
    """Persist simulation records with artifacts and links to the database."""

    now = datetime.now(timezone.utc)

    for sim_create in simulations:
        data = sim_create.model_dump(
            by_alias=False,
            exclude={"artifacts", "links", "created_by", "last_updated_by"},
            exclude_unset=True,
        )

        # Normalize URL
        if data.get("git_repository_url") is not None:
            data["git_repository_url"] = str(data["git_repository_url"])

        sim = Simulation(
            **data,
            created_by=user.id,
            last_updated_by=user.id,
            created_at=now,
            updated_at=now,
        )

        if sim_create.artifacts:
            for artifact in sim_create.artifacts:
                artifact_data = artifact.model_dump(
                    by_alias=False,
                    exclude_unset=True,
                )
                artifact_data["uri"] = str(artifact.uri)
                sim.artifacts.append(Artifact(**artifact_data))

        if sim_create.links:
            for link in sim_create.links:
                link_data = link.model_dump(
                    by_alias=False,
                    exclude_unset=True,
                )
                link_data["url"] = str(link.url)
                sim.links.append(ExternalLink(**link_data))

        db.add(sim)
        db.flush()


def _persist_and_respond_to_ingestion(
    simulations: list[SimulationCreate],
    created_count: int,
    duplicate_count: int,
    errors: list[dict[str, str]],
    source_type: IngestionSourceType,
    source_reference: str,
    machine_id,
    user: User,
    archive_sha256: str,
    db: Session,
) -> IngestionResponse:
    """Persist ingestion metadata and simulations, then return a response.

    This is a shared helper function used by both the path-based and upload-based
    ingestion endpoints.
    """
    error_count = len(errors)
    status_value = _resolve_ingestion_status(created_count, error_count)

    with transaction(db):
        _persist_simulations(simulations, db, user)

        ingestion_create = IngestionCreate(
            source_type=source_type.value,
            source_reference=source_reference,
            machine_id=machine_id,
            triggered_by=user.id,
            status=status_value,
            created_count=created_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
            archive_sha256=archive_sha256,
        )
        ingestion = Ingestion(
            **ingestion_create.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(ingestion)
        db.flush()

    return IngestionResponse(
        created_count=created_count,
        duplicate_count=duplicate_count,
        simulations=simulations,
        errors=errors,
    )
