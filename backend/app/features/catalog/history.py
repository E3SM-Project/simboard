"""Helpers for append-only managed metadata history."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, cast
from uuid import UUID

from app.features.catalog.models import Artifact, Case, Execution, ExternalLink

AuditedEntity = Case | Execution
EntityType = Literal["case", "execution"]


def snapshot_metadata(entity: AuditedEntity, field_names: set[str]) -> dict[str, Any]:
    """Return JSON-safe values for requested editable fields."""
    snapshot: dict[str, Any] = {}

    for field_name in field_names:
        if field_name == "artifacts":
            snapshot[field_name] = [
                _artifact_value(artifact)
                for artifact in cast(Execution, entity).artifacts
            ]
        elif field_name == "links":
            snapshot[field_name] = [_link_value(link) for link in entity.links]
        else:
            snapshot[field_name] = _json_value(getattr(entity, field_name))

    return snapshot


def changed_metadata(
    previous: dict[str, Any], current: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """Return changed fields with their previous and current values."""
    return [
        (field_name, previous[field_name], current[field_name])
        for field_name in previous
        if previous[field_name] != current[field_name]
    ]


def _artifact_value(artifact: Artifact) -> dict[str, Any]:
    return {
        "kind": _json_value(artifact.kind),
        "uri": artifact.uri,
        "label": artifact.label,
        "checksum": artifact.checksum,
        "sizeBytes": artifact.size_bytes,
    }


def _link_value(link: ExternalLink) -> dict[str, Any]:
    return {
        "kind": _json_value(link.kind),
        "url": link.url,
        "label": link.label,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
