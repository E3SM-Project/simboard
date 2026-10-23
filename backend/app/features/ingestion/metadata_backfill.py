"""Narrow updates to existing execution metadata, never ingestion state."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.common.model_dates import ModelDate
from app.features.catalog.enums import ArtifactKind
from app.features.catalog.history import changed_metadata, snapshot_metadata
from app.features.catalog.models import Artifact, Execution, MetadataChange


class MetadataValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_start_date: ModelDate | None = None
    simulation_end_date: ModelDate | None = None
    run_script: str | None = Field(default=None, max_length=1000, min_length=1)
    compset_long_name: str | None = None
    compset_alias: str | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.simulation_start_date and self.simulation_end_date:
            if self.simulation_end_date < self.simulation_start_date:
                raise ValueError("Simulation end precedes start")

        return self


class MetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_name: str = Field(min_length=1)
    record_id: UUID
    case_name: str = Field(min_length=1)
    hpc_username: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    fields: list[Literal["simulation-dates", "run-script", "component-set"]] = Field(
        min_length=1, max_length=3
    )
    values: MetadataValues
    expected: MetadataValues
    overwrite: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def complete_component_set(self):
        if "component-set" in self.fields:
            for label, values in (("values", self.values), ("expected", self.expected)):
                if (
                    not {"compset_long_name", "compset_alias"}
                    <= values.model_fields_set
                ):
                    raise ValueError(f"Explicit component-set pair required in {label}")
            if (
                not self.values.compset_long_name
                or not self.values.compset_long_name.strip()
            ):
                raise ValueError("Required component-set long name missing in values")

        return self


def stored_values(execution: Execution) -> MetadataValues:
    scripts = [a for a in execution.artifacts if a.kind == ArtifactKind.RUN_SCRIPT]
    if len(scripts) > 1:
        raise ValueError("Multiple stored run-script artifacts")

    return MetadataValues(
        simulation_start_date=execution.simulation_start_date,
        simulation_end_date=execution.simulation_end_date,
        run_script=scripts[0].uri if scripts else None,
        compset_long_name=execution.compset_long_name,
        compset_alias=execution.compset_alias,
    )


def _apply_changes(
    db: Session, execution: Execution, changes: dict, editor: UUID
) -> None:
    if not changes:
        return

    fields = {"artifacts" if name == "run_script" else name for name in changes}
    previous = snapshot_metadata(execution, fields)
    for name, change in changes.items():
        if name != "run_script":
            setattr(execution, name, change["after"])
            continue

        script = next(
            (a for a in execution.artifacts if a.kind == ArtifactKind.RUN_SCRIPT), None
        )
        if script is None:
            execution.artifacts.append(
                Artifact(kind=ArtifactKind.RUN_SCRIPT, uri=change["after"])
            )
        else:
            script.uri = change["after"]
            script.checksum = None
            script.size_bytes = None

    now = datetime.now(timezone.utc)
    execution.last_updated_by = editor
    execution.updated_at = now
    db.add_all(
        [
            MetadataChange(
                entity_type="execution",
                entity_id=execution.id,
                field_name=name,
                old_value=before,
                new_value=after,
                editor_id=editor,
                changed_at=now,
                reason="Metadata backfill",
            )
            for name, before, after in changed_metadata(
                previous, snapshot_metadata(execution, fields)
            )
        ]
    )


def _validate_fill_dates(old: MetadataValues, payload: MetadataUpdate) -> None:
    if "simulation-dates" not in payload.fields or payload.overwrite:
        return

    dates = ("simulation_start_date", "simulation_end_date")
    differs = any(
        getattr(old, name) is not None
        and getattr(payload.values, name) is not None
        and getattr(old, name) != getattr(payload.values, name)
        for name in dates
    )
    fills = any(
        getattr(old, name) is None and getattr(payload.values, name) is not None
        for name in dates
    )

    if differs and fills:
        raise ValueError(
            "Cannot fill dates from a different interval without overwrite"
        )


def update_metadata(
    db: Session, execution: Execution, payload: MetadataUpdate, editor: UUID
) -> dict:
    """Caller locks the execution; compare and write only requested values."""
    old = stored_values(execution)
    _validate_fill_dates(old, payload)

    changes = {}
    names = []
    if "simulation-dates" in payload.fields:
        names.extend(["simulation_start_date", "simulation_end_date"])
    if "run-script" in payload.fields:
        names.append("run_script")
    names.extend(_component_set_fields(old, payload))

    for name in names:
        before = getattr(old, name)
        after = getattr(payload.values, name)
        if before == after or (after is None and name != "compset_alias"):
            continue
        if before is not None and not payload.overwrite:
            continue
        if before != getattr(payload.expected, name):
            raise ValueError(f"Stored {name} changed; rerun backfill")
        changes[name] = {"before": before, "after": after}

    resulting = old.model_dump()
    resulting.update({name: change["after"] for name, change in changes.items()})
    MetadataValues.model_validate(resulting)

    if not payload.dry_run:
        _apply_changes(db, execution, changes, editor)

    return {
        "record_id": str(execution.id),
        "outcome": "changed" if changes else "unchanged",
        "changes": changes,
        "dry_run": payload.dry_run,
    }


def _component_set_fields(old: MetadataValues, payload: MetadataUpdate) -> list[str]:
    if "component-set" not in payload.fields:
        return []

    fields = ["compset_long_name", "compset_alias"]
    # Compare the pair, even if one member is unchanged. Never clear an alias
    # against a long name that changed after source observation.
    for name in fields:
        before = getattr(old, name)
        if before != getattr(payload.expected, name) and before != getattr(
            payload.values, name
        ):
            raise ValueError(f"Stored {name} changed; rerun backfill")

    # Treat the pair atomically when fill-only mode cannot replace a member.
    needs_overwrite = any(
        getattr(old, name) is not None
        and getattr(old, name) != getattr(payload.values, name)
        for name in fields
    )

    return fields if payload.overwrite or not needs_overwrite else []
