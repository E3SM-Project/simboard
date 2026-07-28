from datetime import date, datetime, timezone
from uuid import UUID

from app.features.catalog.enums import ArtifactKind, ExecutionStatus, ExternalLinkKind
from app.features.catalog.history import changed_metadata, snapshot_metadata
from app.features.catalog.models import Artifact, Execution, ExternalLink


def test_snapshot_metadata_converts_nested_values_to_json_safe_types() -> None:
    entity_id = UUID("d4e426cb-01e2-4c29-99d4-bcbac5dd69df")
    changed_at = datetime(2026, 7, 28, 12, 30, tzinfo=timezone.utc)
    execution = Execution(
        extra={
            "status": ExecutionStatus.COMPLETED,
            "entity_id": entity_id,
            "dates": [date(2026, 7, 28), changed_at],
            "label": "metadata",
        }
    )

    assert snapshot_metadata(execution, {"extra"}) == {
        "extra": {
            "status": "completed",
            "entity_id": str(entity_id),
            "dates": ["2026-07-28", "2026-07-28T12:30:00+00:00"],
            "label": "metadata",
        }
    }


def test_snapshot_metadata_serializes_resources_and_scalar_fields() -> None:
    execution = Execution(status=ExecutionStatus.RUNNING)
    execution.artifacts = [
        Artifact(
            kind=ArtifactKind.OUTPUT,
            uri="s3://bucket/output",
            label="Output",
            checksum="sha256:abc",
            size_bytes=42,
        )
    ]
    execution.links = [
        ExternalLink(
            kind=ExternalLinkKind.DOCS,
            url="https://example.com/docs",
            label="Documentation",
        )
    ]

    assert snapshot_metadata(execution, {"artifacts", "links", "status"}) == {
        "artifacts": [
            {
                "kind": "output",
                "uri": "s3://bucket/output",
                "label": "Output",
                "checksum": "sha256:abc",
                "sizeBytes": 42,
            }
        ],
        "links": [
            {
                "kind": "docs",
                "url": "https://example.com/docs",
                "label": "Documentation",
            }
        ],
        "status": "running",
    }


def test_changed_metadata_returns_only_changed_fields() -> None:
    assert changed_metadata(
        {"description": "before", "status": "running"},
        {"description": "after", "status": "running"},
    ) == [("description", "before", "after")]
