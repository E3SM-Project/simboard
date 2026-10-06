"""Resolve observed directories to existing catalog identities."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.features.catalog.models import Case, Execution
from app.features.catalog.source_directories import persist_source_directory
from app.features.ingestion.schemas import SourceDirectoryObservation


def persist_observed_directories(
    db: Session,
    machine_id: UUID,
    directories: list[SourceDirectoryObservation],
    *,
    strict: bool = True,
) -> list[SourceDirectoryObservation]:
    """Resolve before writing; report missing owners without creating them."""
    resolved: list[tuple[SourceDirectoryObservation, Case, Execution]] = []
    unresolved: list[SourceDirectoryObservation] = []
    for directory in directories:
        pair = (
            db.query(Case, Execution)
            .join(Execution, Execution.case_id == Case.id)
            .filter(
                Case.machine_id == machine_id,
                Case.name == directory.case_name,
                Case.hpc_username == directory.hpc_username,
                Execution.execution_id == directory.execution_id,
            )
            .one_or_none()
        )
        if pair is None:
            if strict:
                raise ValueError(
                    "Unresolved source directory: "
                    f"{directory.case_name!r}, user={directory.hpc_username!r}, "
                    f"execution={directory.execution_id!r}, path={directory.execution_path!r}"
                )
            unresolved.append(directory)
            continue
        case, execution = pair
        resolved.append((directory, case, execution))

    for directory, case, execution in resolved:
        persist_source_directory(db, case, directory.kind, directory.case_path)
        persist_source_directory(
            db, execution, directory.kind, directory.execution_path
        )
    return unresolved
