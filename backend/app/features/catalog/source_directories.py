"""Idempotent persistence of observed performance-data directories."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.features.catalog.enums import SourceDirectoryKind
from app.features.catalog.models import Case, Execution, SourceDirectory


def persist_source_directory(
    db: Session,
    owner: Case | Execution,
    kind: SourceDirectoryKind,
    path: str,
) -> None:
    """Retain distinct paths without changing owner identity or existing paths."""
    owner_field = "case_id" if isinstance(owner, Case) else "execution_id"
    db.execute(
        insert(SourceDirectory)
        .values(**{owner_field: owner.id}, kind=kind, path=path)
        .on_conflict_do_nothing()
    )
