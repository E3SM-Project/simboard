from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.features.simulation.link_utils import merge_execution_and_case_links
from app.features.simulation.models import Artifact, Execution, ExternalLink

SNAPSHOT_TRUNCATED_CAVEAT = (
    "The metadata snapshot was truncated to fit the assistant size budget. "
    "Some artifacts, links, or long text fields were omitted."
)


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _isoformat(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


class SnapshotArtifact(BaseModel):
    kind: str
    uri: str
    label: str | None = None


class SnapshotLink(BaseModel):
    kind: str
    url: str
    label: str | None = None


class SnapshotExecutionFields(BaseModel):
    id: str
    execution_id: str
    description: str | None = None
    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str
    simulation_type: str
    status: str
    campaign: str | None = None
    experiment_type: str | None = None
    initialization_type: str
    simulation_start_date: str | None = None
    simulation_end_date: str | None = None
    run_start_date: str | None = None
    run_end_date: str | None = None
    compiler: str | None = None
    key_features: str | None = None
    known_issues: str | None = None
    notes_markdown: str | None = None
    git_repository_url: str | None = None
    git_branch: str | None = None
    git_tag: str | None = None
    git_commit_hash: str | None = None
    case_hash: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SnapshotCaseFields(BaseModel):
    name: str
    case_group: str | None = None


class SnapshotMachineFields(BaseModel):
    name: str


class ExecutionSnapshot(BaseModel):
    execution: SnapshotExecutionFields
    case: SnapshotCaseFields
    machine: SnapshotMachineFields | None = None
    artifacts: list[SnapshotArtifact] = Field(default_factory=list)
    links: list[SnapshotLink] = Field(default_factory=list)
    snapshot_caveats: list[str] = Field(default_factory=list)


class SnapshotBudgetExceededError(ValueError):
    def __init__(self, snapshot: ExecutionSnapshot, max_chars: int) -> None:
        size = _snapshot_size(snapshot)
        super().__init__(
            f"Snapshot size {size} exceeds budget {max_chars} even after all "
            "trimming. Required fields are too large to fit within the configured "
            "limit."
        )
        self.snapshot = snapshot
        self.max_chars = max_chars


@dataclass(frozen=True)
class _SnapshotSizeBudget:
    max_chars: int


def _sorted_artifacts(items: Iterable[Artifact]) -> list[SnapshotArtifact]:
    return sorted(
        [
            SnapshotArtifact(
                kind=_enum_value(item.kind) or "unknown",
                uri=item.uri,
                label=item.label,
            )
            for item in items
        ],
        key=lambda item: (item.kind, item.label or "", item.uri),
    )


def _sorted_links(items: Iterable[ExternalLink]) -> list[SnapshotLink]:
    return sorted(
        [
            SnapshotLink(
                kind=_enum_value(item.kind) or "unknown",
                url=item.url,
                label=item.label,
            )
            for item in items
        ],
        key=lambda item: (item.kind, item.label or "", item.url),
    )


def _snapshot_size(snapshot: ExecutionSnapshot) -> int:
    return len(snapshot.model_dump_json(exclude_none=True))


def _add_truncation_caveat(snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
    if SNAPSHOT_TRUNCATED_CAVEAT in snapshot.snapshot_caveats:
        return snapshot
    return snapshot.model_copy(
        update={
            "snapshot_caveats": [*snapshot.snapshot_caveats, SNAPSHOT_TRUNCATED_CAVEAT]
        }
    )


def _trim_snapshot_strings(snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
    execution = snapshot.execution.model_copy(
        update={
            "notes_markdown": None,
            "description": None,
            "key_features": None,
            "known_issues": None,
            "extra": {},
        }
    )
    return snapshot.model_copy(update={"execution": execution})


def _apply_size_budget(
    snapshot: ExecutionSnapshot,
    budget: _SnapshotSizeBudget,
) -> ExecutionSnapshot:
    if _snapshot_size(snapshot) <= budget.max_chars:
        return snapshot

    trimmed = snapshot.model_copy(deep=True)

    while _snapshot_size(trimmed) > budget.max_chars and (
        trimmed.artifacts or trimmed.links
    ):
        if len(trimmed.artifacts) >= len(trimmed.links) and trimmed.artifacts:
            trimmed = trimmed.model_copy(update={"artifacts": trimmed.artifacts[:-1]})
        elif trimmed.links:
            trimmed = trimmed.model_copy(update={"links": trimmed.links[:-1]})

    if _snapshot_size(trimmed) > budget.max_chars:
        trimmed = _trim_snapshot_strings(trimmed)

    if _snapshot_size(trimmed) > budget.max_chars and trimmed.artifacts:
        trimmed = trimmed.model_copy(update={"artifacts": []})

    if _snapshot_size(trimmed) > budget.max_chars and trimmed.links:
        trimmed = trimmed.model_copy(update={"links": []})

    trimmed = _add_truncation_caveat(trimmed)

    if _snapshot_size(trimmed) > budget.max_chars:
        raise SnapshotBudgetExceededError(trimmed, budget.max_chars)

    return trimmed


def build_execution_snapshot(
    execution: Execution,
    *,
    max_chars: int | None = None,
) -> ExecutionSnapshot:
    merged_links = merge_execution_and_case_links(
        execution.links,
        execution.case.links,
    )
    snapshot = ExecutionSnapshot(
        execution=SnapshotExecutionFields(
            id=str(execution.id),
            execution_id=execution.execution_id,
            description=execution.description,
            compset=execution.compset,
            compset_alias=execution.compset_alias,
            grid_name=execution.grid_name,
            grid_resolution=execution.grid_resolution,
            simulation_type=_enum_value(execution.simulation_type) or "unknown",
            status=_enum_value(execution.status) or "unknown",
            campaign=execution.campaign,
            experiment_type=execution.experiment_type,
            initialization_type=execution.initialization_type,
            simulation_start_date=_isoformat(execution.simulation_start_date),
            simulation_end_date=_isoformat(execution.simulation_end_date),
            run_start_date=_isoformat(execution.run_start_date),
            run_end_date=_isoformat(execution.run_end_date),
            compiler=execution.compiler,
            key_features=execution.key_features,
            known_issues=execution.known_issues,
            notes_markdown=execution.notes_markdown,
            git_repository_url=execution.git_repository_url,
            git_branch=execution.git_branch,
            git_tag=execution.git_tag,
            git_commit_hash=execution.git_commit_hash,
            case_hash=execution.case_hash,
            extra=dict(execution.extra or {}),
        ),
        case=SnapshotCaseFields(
            name=execution.case.name,
            case_group=execution.case.case_group,
        ),
        machine=(
            SnapshotMachineFields(name=execution.case.machine.name)
            if execution.case.machine is not None
            else None
        ),
        artifacts=_sorted_artifacts(execution.artifacts),
        links=_sorted_links(merged_links),
        snapshot_caveats=[],
    )

    size_budget = _SnapshotSizeBudget(
        max_chars=max_chars or settings.assistant_snapshot_max_chars
    )
    return _apply_size_budget(snapshot, size_budget)
