import hashlib
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.ingestion.ingest import IngestArchiveResult, ingest_archive
from app.features.ingestion.models import Ingestion, IngestionSourceType
from app.features.ingestion.parsers.parser import ArchiveValidationError
from app.features.ingestion.schemas import (
    IngestFromHpcUploadRequest,
    IngestFromPathRequest,
    IngestionCreate,
    IngestionResponse,
    IngestionSimulationSummary,
    IngestionStateCase,
    IngestionStateResponse,
    IngestionStatus,
)
from app.features.machine.utils import resolve_machine_by_name
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation
from app.features.simulation.schemas import SimulationCreate
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
STATEFUL_INGESTION_SOURCE_TYPES = (
    IngestionSourceType.HPC_PATH,
    IngestionSourceType.HPC_UPLOAD,
)


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
) -> IngestionResponse:
    """Ingest an archive from a filesystem path and persist simulations.

    NOTE: Arbitrary filesystem paths are currently permitted to support HPC
    ingestion workflows (e.g., NERSC). This endpoint is restricted to users with
    the ADMIN or SERVICE_ACCOUNT role.
    Path artifacts parsed from the archive are treated as opaque provenance
    metadata and stored exactly as they appear in the archive metadata.

    TODO: Consider enforcing that archive_path must reside within a configured
    base directory (e.g., a designated HPC storage or ingestion directory)
    before exposing this endpoint beyond a trusted environment.

    Parameters
    ----------
    payload : IngestFromPathRequest
        Request payload containing the archive path, machine name, and optional
        HPC username for provenance.
    db : Session
        Active SQLAlchemy database session used for persistence.
    user : User
        Authenticated user who initiated the ingestion, used for permission
        checks and recorded as the trigger of the ingestion.

    Returns
    -------
    IngestionResponse
        Response model summarizing ingestion results, including counts,
        created simulations, and any recorded errors.
    """
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and service accounts may ingest from filesystem paths.",
        )

    machine = _resolve_request_machine(db, payload.machine_name)

    archive_path = Path(payload.archive_path)
    _validate_archive_path(archive_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        ingest_result = _run_ingest_archive(
            archive_path=str(archive_path),
            output_dir=tmpdir,
            db=db,
            hpc_username=payload.hpc_username,
        )

    response = _process_ingestion(
        ingest_result=ingest_result,
        source_type=IngestionSourceType.HPC_PATH,
        source_reference=str(archive_path),
        machine_id=machine.id,
        user=user,
        archive_sha256=None,
        hpc_username=payload.hpc_username,
        processed_execution_ids=payload.processed_execution_ids,
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
def ingest_from_upload(
    file: UploadFile = File(...),
    machine_name: str = Form(...),
    hpc_username: str | None = Form(None),
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> IngestionResponse:
    """Ingest an archive via file upload and persist simulations.

    Path artifacts parsed from uploaded archives are treated as opaque remote
    provenance metadata. SimBoard stores the filesystem paths exactly as
    reported in the archive metadata without validating them on the API host.

    Parameters
    ----------
    file : UploadFile
        Uploaded archive file, expected to be .zip, .tar.gz, or .tgz
    machine_name : str
        Name of the machine associated with this ingestion, used to look up the
        corresponding Machine record in the database.
    hpc_username : str, optional
        HPC username for provenance (trusted, informational only), included in
        the created Simulation records if provided.
    db : Session
        Active SQLAlchemy database session used for persistence.
    user : User
        Authenticated user who initiated the ingestion, used for recorded as the
        trigger of the ingestion.

    Returns
    -------
    IngestionResponse
        Response model summarizing ingestion results, including counts,
        created simulations, and any recorded errors.
    """
    machine = _resolve_request_machine(db, machine_name)

    _validate_upload_file(file)
    filename = file.filename
    if filename is None:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / filename
            sha256_hex = _save_uploaded_file_and_hash(file, archive_path)

            ingest_result = _run_ingest_archive(
                archive_path=str(archive_path),
                output_dir=tmpdir,
                db=db,
                strict_validation=True,
                hpc_username=hpc_username,
            )

        if ingest_result.errors:
            _raise_archive_validation_error(ingest_result.errors)

        response = _process_ingestion(
            ingest_result=ingest_result,
            source_type=IngestionSourceType.BROWSER_UPLOAD,
            source_reference=filename,
            machine_id=machine.id,
            user=user,
            archive_sha256=sha256_hex,
            hpc_username=hpc_username,
            db=db,
        )

        return response
    finally:
        try:
            file.file.close()
        except Exception:
            pass


@router.post(
    "/from-hpc-upload",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Automated HPC upload ingestion completed."},
        400: {"description": "Invalid input or upload file."},
        403: {
            "description": (
                "Forbidden: only administrators and service accounts may upload "
                "automated HPC archives."
            )
        },
        404: {"description": "Machine not found."},
        409: {"description": "Conflict: ingestion error."},
        413: {"description": "File too large."},
        500: {"description": "Internal server error."},
    },
)
def ingest_from_hpc_upload(
    file: UploadFile = File(...),
    machine_name: str = Form(...),
    case_path: str = Form(...),
    hpc_username: str | None = Form(None),
    processed_execution_ids: list[str] | None = Form(None),
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> IngestionResponse:
    """Ingest one service-account HPC archive upload with path-style semantics.

    Parameters
    ----------
    file : UploadFile
        Uploaded archive file, expected to be .zip, .tar.gz, or .tgz
    machine_name : str
        Name of the machine associated with this ingestion, used to look up the
        corresponding Machine record in the database.
    case_path : str
        Case path string parsed from the archive metadata, used as the
        source_reference for this ingestion and to validate that exactly one case
        is created from the archive.
    hpc_username : str, optional
        HPC username for provenance (trusted, informational only), included in
        the created Simulation records if provided.
    processed_execution_ids : list[str], optional
        Full discovered execution IDs for this uploaded case. Scheduler jobs send
        this repeated form field so SimBoard can persist dedupe state even when
        the upload produces only duplicates or partial results.
    db : Session
        Active SQLAlchemy database session used for persistence.
    user : User
        Authenticated user who initiated the ingestion, used for permission
        checks and recorded as the trigger of the ingestion.
    """
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only administrators and service accounts may upload automated "
                "HPC archives."
            ),
        )

    payload = _build_hpc_upload_payload(
        machine_name=machine_name,
        case_path=case_path,
        hpc_username=hpc_username,
        processed_execution_ids=processed_execution_ids,
    )
    machine = _resolve_request_machine(db, payload.machine_name)

    _validate_upload_file(file)
    filename = file.filename
    if filename is None:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / filename
            sha256_hex = _save_uploaded_file_and_hash(file, archive_path)

            ingest_result = _run_ingest_archive(
                archive_path=str(archive_path),
                output_dir=tmpdir,
                db=db,
                hpc_username=payload.hpc_username,
            )

        _validate_single_case_upload_ingest_result(ingest_result, payload.case_path)

        return _process_ingestion(
            ingest_result=ingest_result,
            source_type=IngestionSourceType.HPC_UPLOAD,
            source_reference=payload.case_path,
            machine_id=machine.id,
            user=user,
            archive_sha256=sha256_hex,
            hpc_username=payload.hpc_username,
            processed_execution_ids=payload.processed_execution_ids,
            db=db,
        )
    finally:
        try:
            file.file.close()
        except Exception:
            pass


@router.get(
    "/state",
    response_model=IngestionStateResponse,
    responses={
        200: {"description": "Database-backed ingestion state for one machine."},
        403: {
            "description": "Forbidden: only administrators can read ingestion state."
        },
        404: {"description": "Machine not found."},
    },
)
def get_ingestion_state(
    machine_name: str,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> IngestionStateResponse:
    """Return known ingested execution IDs for one machine."""
    if user.role not in (UserRole.ADMIN, UserRole.SERVICE_ACCOUNT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and service accounts may read ingestion state.",
        )

    machine = _resolve_request_machine(db, machine_name)

    return _build_ingestion_state_response(db, machine.id, machine.name)


def _resolve_request_machine(db: Session, machine_name: str):
    machine = resolve_machine_by_name(db, machine_name)
    if not machine:
        raise HTTPException(
            status_code=404, detail=f"Machine '{machine_name}' not found."
        )

    return machine


def _build_hpc_upload_payload(
    *,
    machine_name: str,
    case_path: str,
    hpc_username: str | None,
    processed_execution_ids: list[str] | None,
) -> IngestFromHpcUploadRequest:
    normalized_execution_ids = _normalize_processed_execution_ids(
        processed_execution_ids or []
    )

    try:
        return IngestFromHpcUploadRequest(
            machine_name=machine_name,
            case_path=case_path.strip(),
            hpc_username=hpc_username,
            processed_execution_ids=normalized_execution_ids or [],
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(),
        ) from exc


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


def _build_ingestion_state_response(
    db: Session,
    machine_id: UUID,
    machine_name: str,
) -> IngestionStateResponse:
    execution_ids_by_case: dict[str, set[str]] = defaultdict(set)
    ingestion_rows = (
        db.query(
            Ingestion.id, Ingestion.source_reference, Ingestion.processed_execution_ids
        )
        .filter(
            Ingestion.source_type.in_(STATEFUL_INGESTION_SOURCE_TYPES),
            Ingestion.machine_id == machine_id,
        )
        .order_by(Ingestion.source_reference.asc(), Ingestion.created_at.asc())
        .all()
    )
    requires_legacy_fallback = False

    for _ingestion_id, case_path, processed_execution_ids in ingestion_rows:
        if not case_path:
            continue

        normalized_execution_ids = _normalize_processed_execution_ids(
            processed_execution_ids
        )
        if normalized_execution_ids is None:
            requires_legacy_fallback = True
            continue

        execution_ids_by_case[case_path].update(normalized_execution_ids)

    if requires_legacy_fallback:
        simulation_rows = (
            db.query(Ingestion.source_reference, Simulation.execution_id)
            .join(Simulation, Simulation.ingestion_id == Ingestion.id)
            .filter(
                Ingestion.source_type.in_(STATEFUL_INGESTION_SOURCE_TYPES),
                Ingestion.machine_id == machine_id,
                or_(
                    Ingestion.processed_execution_ids.is_(None),
                    func.jsonb_typeof(Ingestion.processed_execution_ids) == "null",
                ),
            )
            .order_by(Ingestion.source_reference.asc(), Simulation.execution_id.asc())
            .all()
        )

        for case_path, execution_id in simulation_rows:
            if not case_path or not execution_id:
                continue
            execution_ids_by_case[case_path].add(execution_id)

    cases = {
        case_path: IngestionStateCase(
            processed_execution_ids=processed_execution_ids,
            fingerprint=_compute_execution_fingerprint(processed_execution_ids),
        )
        for case_path, processed_execution_ids in (
            (case_path, sorted(execution_ids))
            for case_path, execution_ids in sorted(execution_ids_by_case.items())
        )
    }

    return IngestionStateResponse(machine_name=machine_name, cases=cases)


def _compute_execution_fingerprint(execution_ids: list[str]) -> str:
    digest = hashlib.sha256()

    for execution_id in execution_ids:
        digest.update(execution_id.encode("utf-8"))
        digest.update(b"\n")

    return digest.hexdigest()


def _normalize_processed_execution_ids(raw_execution_ids: Any) -> list[str] | None:
    if raw_execution_ids is None:
        return None
    if not isinstance(raw_execution_ids, list):
        return None

    normalized_values = {
        value.strip()
        for value in raw_execution_ids
        if isinstance(value, str) and value.strip()
    }
    return sorted(normalized_values)


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


def _save_uploaded_file_and_hash(
    file: UploadFile,
    archive_path: Path,
) -> str:
    sha256_hash = hashlib.sha256()
    total_bytes = 0

    with archive_path.open("wb") as out_file:
        for chunk in iter(lambda: file.file.read(8192), b""):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(status_code=413, detail="File too large")

            out_file.write(chunk)
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def _run_ingest_archive(
    archive_path: str,
    output_dir: str,
    db: Session,
    *,
    strict_validation: bool = False,
    hpc_username: str | None = None,
) -> IngestArchiveResult:
    try:
        return ingest_archive(
            archive_path=archive_path,
            output_dir=output_dir,
            db=db,
            strict_validation=strict_validation,
            hpc_username=hpc_username,
        )
    except ArchiveValidationError as exc:
        _raise_archive_validation_error(exc.errors)
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


def _raise_archive_validation_error(errors: list[dict[str, str]]) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "message": "Archive validation failed.",
            "errors": errors,
        },
    )


def _validate_single_case_upload_ingest_result(
    ingest_result: IngestArchiveResult,
    case_path: str,
) -> None:
    created_case_ids = {
        simulation.case_id
        for simulation in ingest_result.simulations
        if simulation.case_id is not None
    }
    if len(created_case_ids) <= 1:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Automated HPC upload archives must contain exactly one case. "
            f"Received created simulations for multiple cases under '{case_path}'."
        ),
    )


def _process_ingestion(
    ingest_result: IngestArchiveResult,
    source_type: IngestionSourceType,
    source_reference: str,
    machine_id: UUID,
    user: User,
    archive_sha256: str | None,
    db: Session,
    hpc_username: str | None = None,
    processed_execution_ids: list[str] | None = None,
) -> IngestionResponse:
    """Finalize and persist an ingestion operation.

    This function completes the ingestion workflow after archive parsing has
    succeeded. It determines ingestion status, persists simulation records and
    ingestion metadata within a transactional boundary, and returns a structured
    response model.

    Parameters
    ----------
    ingest_result : IngestArchiveResult
        Structured result produced by the archive ingestion step, including
        parsed simulations, duplicate counts, and per-execution errors.
    source_type : IngestionSourceType
        Enumeration indicating the ingestion source (e.g., HPC_PATH,
        HPC_UPLOAD).
    source_reference : str
        Identifier for the ingestion source, such as a filesystem path
        or uploaded filename.
    machine_id : UUID
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
            processed_execution_ids=processed_execution_ids,
        )
        ingestion = Ingestion(
            **ingestion_create.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(ingestion)
        db.flush()

        created_sims = _persist_simulations(
            ingestion.id, ingest_result.simulations, db, user, hpc_username
        )

    return IngestionResponse(
        created_count=ingest_result.created_count,
        duplicate_count=ingest_result.duplicate_count,
        simulations=_build_ingestion_simulation_summaries(created_sims, db),
        errors=ingest_result.errors,
    )


def _resolve_ingestion_status(created_count: int, error_count: int) -> str:
    if error_count == 0 and created_count > 0:
        return IngestionStatus.SUCCESS.value

    if error_count > 0 and created_count > 0:
        return IngestionStatus.PARTIAL.value

    return IngestionStatus.FAILED.value


def _persist_simulations(
    ingestion_id: UUID,
    simulations: list[SimulationCreate],
    db: Session,
    user: User,
    hpc_username: str | None = None,
) -> list[Simulation]:
    """Persist simulation records with artifacts and links to the database.

    Parameters
    ----------
    ingestion_id : UUID
        Identifier of the parent ingestion record to associate with each
        simulation.
    simulations : list[SimulationCreate]
        List of simulation data to persist, including nested artifacts and
        links.
    db : Session
        Active SQLAlchemy database session used for persistence.
    user : User
        Authenticated user who initiated the ingestion, set as creator and
        last updater of each simulation record.
    hpc_username : str | None, optional
        HPC username for provenance (trusted, informational only)
    """
    now = datetime.now(timezone.utc)
    created_sims: list[Simulation] = []

    for sim_create in simulations:
        data = sim_create.model_dump(
            by_alias=False,
            exclude={"artifacts", "links", "created_by", "last_updated_by"},
            exclude_unset=True,
        )

        if data.get("git_repository_url") is not None:
            data["git_repository_url"] = str(data["git_repository_url"])

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
        created_sims.append(sim)

    db.flush()
    return created_sims


def _build_ingestion_simulation_summaries(
    created_sims: list[Simulation], db: Session
) -> list[IngestionSimulationSummary]:
    if not created_sims:
        return []

    case_ids = list({sim.case_id for sim in created_sims})
    cases = {
        case.id: case for case in db.query(Case).filter(Case.id.in_(case_ids)).all()
    }

    return [
        IngestionSimulationSummary(
            id=sim.id,
            case_id=sim.case_id,
            case_name=cases[sim.case_id].name,
            execution_id=sim.execution_id,
        )
        for sim in created_sims
        if sim.id is not None and sim.case_id in cases
    ]
