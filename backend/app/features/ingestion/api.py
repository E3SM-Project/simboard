import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.ingest import IngestArchiveResult, ingest_archive
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
    if user.role not in ("admin", "service_account"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and service accounts may ingest from filesystem paths.",
        )

    machine = db.query(Machine).filter(Machine.name == payload.machine_name).first()

    if not machine:
        raise HTTPException(
            status_code=404, detail=f"Machine '{payload.machine_name}' not found."
        )

    archive_path = Path(payload.archive_path)
    _validate_archive_path(archive_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        ingest_result = _run_ingest_archive(
            archive_path=str(archive_path), output_dir=tmpdir, db=db
        )

    response = _process_ingestion(
        ingest_result=ingest_result,
        source_type=IngestionSourceType.HPC_PATH,
        source_reference=str(archive_path),
        machine_id=machine.id,
        user=user,
        archive_sha256=None,
        hpc_username=payload.hpc_username,
        db=db,
    )

    return response


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
    hpc_username: str | None = Form(None),
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

            ingest_result = _run_ingest_archive(
                archive_path=str(archive_path), output_dir=tmpdir, db=db
            )

        response = _process_ingestion(
            ingest_result=ingest_result,
            source_type=IngestionSourceType.HPC_UPLOAD,
            source_reference=filename,
            machine_id=machine.id,
            user=user,
            archive_sha256=sha256_hex,
            hpc_username=hpc_username,
            db=db,
        )

        return response
    finally:
        file.file.close()


def _validate_archive_path(archive_path: Path) -> None:
    if not archive_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive path '{archive_path}' does not exist.",
        )

    if not (archive_path.is_file() or archive_path.is_dir()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Archive path '{archive_path}' must be a file or directory."),
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
            detail="Failed to compute checksum",
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
) -> IngestArchiveResult:
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


def _process_ingestion(
    ingest_result: IngestArchiveResult,
    source_type: IngestionSourceType,
    source_reference: str,
    machine_id: uuid.UUID,
    user: User,
    archive_sha256: str | None,
    db: Session,
    hpc_username: str | None = None,
) -> IngestionResponse:
    """
    Finalize and persist an ingestion operation.

    This function completes the ingestion workflow after archive parsing
    has succeeded. It determines ingestion status, persists simulation
    records and ingestion metadata within a transactional boundary, and
    returns a structured response model.

    Parameters
    ----------
    ingest_result : IngestArchiveResult
        Structured result produced by the archive ingestion step, including
        parsed simulations, duplicate counts, and per-experiment errors.
    source_type : IngestionSourceType
        Enumeration indicating the ingestion source (e.g., HPC_PATH,
        HPC_UPLOAD).
    source_reference : str
        Identifier for the ingestion source, such as a filesystem path
        or uploaded filename.
    machine_id : uuid.UUID
        Identifier of the machine associated with this ingestion.
    user : User
        Authenticated user who initiated the ingestion.
    archive_sha256 : str
        SHA256 checksum of the processed archive.
    db : Session
        Active SQLAlchemy database session used for persistence.
    hpc_username : str | None, optional
        HPC username for provenance (trusted, informational only)

    Returns
    -------
    IngestionResponse
        Response model summarizing ingestion results, including counts,
        created simulations, and any recorded errors.
    """
    error_count = len(ingest_result.errors)
    status_value = _resolve_ingestion_status(ingest_result.created_count, error_count)

    with transaction(db):
        ingestion_create = IngestionCreate(
            source_type=source_type.value,
            source_reference=source_reference,
            machine_id=machine_id,
            triggered_by=user.id,
            status=status_value,
            created_count=ingest_result.created_count,
            duplicate_count=ingest_result.duplicate_count,
            error_count=error_count,
            archive_sha256=archive_sha256,
        )
        ingestion = Ingestion(
            **ingestion_create.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(ingestion)
        db.flush()

        _persist_simulations(
            cast(uuid.UUID, ingestion.id),
            ingest_result.simulations,
            db,
            user,
            hpc_username,
        )

    return IngestionResponse(
        created_count=ingest_result.created_count,
        duplicate_count=ingest_result.duplicate_count,
        simulations=ingest_result.simulations,
        errors=ingest_result.errors,
    )


def _resolve_ingestion_status(created_count: int, error_count: int) -> str:
    if error_count == 0 and created_count > 0:
        return IngestionStatus.SUCCESS.value

    if error_count > 0 and created_count > 0:
        return IngestionStatus.PARTIAL.value

    return IngestionStatus.FAILED.value


def _persist_simulations(
    ingestion_id: uuid.UUID,
    simulations: list[SimulationCreate],
    db: Session,
    user: User,
    hpc_username: str | None = None,
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

        # Set hpc_username if provided
        if hpc_username is not None:
            data["hpc_username"] = hpc_username

        sim = Simulation(
            **data,
            ingestion_id=ingestion_id,
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
