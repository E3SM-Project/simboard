from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, HttpUrl, computed_field

from app.schemas.artifact import ArtifactCreate, ArtifactOut
from app.schemas.base import CamelInBaseModel, CamelOutBaseModel
from app.schemas.link import ExternalLinkCreate, ExternalLinkOut
from app.schemas.machine import MachineOut


class SimulationCreate(CamelInBaseModel):
    # Configuration
    # ~~~~~~~~~~~~~~
    name: str = Field(..., description="Name of the simulation")
    case_name: str = Field(..., description="Case name associated with the simulation")
    description: str | None = Field(
        None, description="Optional description of the simulation"
    )
    compset: str = Field(..., description="Component set used in the simulation")
    compset_alias: str = Field(..., description="Alias for the component set")
    grid_name: str = Field(..., description="Grid name used in the simulation")
    grid_resolution: str = Field(
        ..., description="Grid resolution used in the simulation"
    )
    parent_simulation_id: UUID | None = Field(
        None, description="Optional ID of the parent simulation"
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: str = Field(..., description="Type of the simulation")
    status: str = Field(..., description="Current status of the simulation")
    campaign_id: str | None = Field(
        None, description="Optional ID of the associated campaign"
    )
    experiment_type_id: str | None = Field(
        None, description="Optional ID of the experiment type"
    )
    initialization_type: str = Field(
        ..., description="Initialization type for the simulation"
    )
    group_name: str | None = Field(
        None, description="Optional group name associated with the simulation"
    )

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID = Field(
        ..., description="ID of the machine used for the simulation"
    )
    simulation_start_date: datetime = Field(
        ..., description="Start date of the simulation"
    )
    simulation_end_date: datetime | None = Field(
        None, description="Optional end date of the simulation"
    )
    run_start_date: datetime | None = Field(
        None, description="Optional start date of the simulation run"
    )
    run_end_date: datetime | None = Field(
        None, description="Optional end date of the simulation run"
    )
    compiler: str | None = Field(
        None, description="Optional compiler used for the simulation"
    )

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = Field(
        None, description="Optional key features of the simulation"
    )
    known_issues: str | None = Field(
        None, description="Optional known issues with the simulation"
    )
    notes_markdown: str | None = Field(
        None, description="Optional additional notes in markdown format"
    )

    # Version control
    # ~~~~~~~~~~~~~~~
    git_repository_url: HttpUrl | None = Field(
        None, description="Optional Git repository URL"
    )
    git_branch: str | None = Field(
        None, description="Optional Git branch name associated with the simulation"
    )
    git_tag: str | None = Field(None, description="Optional Git tag for the simulation")
    git_commit_hash: str | None = Field(
        None, description="Optional Git commit hash associated with the simulation"
    )

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: str | None = Field(
        None, description="User who created the simulation, defined at creation time."
    )
    last_updated_by: str | None = Field(
        None,
        description="User who last updated the simulation, defined at update time.",
    )

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: dict = Field(
        default_factory=dict,
        description="Optional extra metadata in flexible dictionary/JSON format",
    )

    # Relationships
    # ~~~~~~~~~~~~~~
    artifacts: list[ArtifactCreate] = Field(
        default_factory=list,
        description="Optional list of artifacts associated with the simulation",
    )
    links: list[ExternalLinkCreate] = Field(
        default_factory=list,
        description="Optional list of external links associated with the simulation",
    )


class SimulationOut(CamelOutBaseModel):
    id: UUID = Field(..., description="The unique identifier of the simulation.")

    # Configuration
    # ~~~~~~~~~~~~~~
    name: str = Field(..., description="Name of the simulation")
    case_name: str = Field(..., description="Case name associated with the simulation")
    description: str | None = Field(
        None, description="Optional description of the simulation"
    )
    compset: str = Field(..., description="Component set used in the simulation")
    compset_alias: str = Field(..., description="Alias for the component set")
    grid_name: str = Field(..., description="Grid name used in the simulation")
    grid_resolution: str = Field(
        ..., description="Grid resolution used in the simulation"
    )
    parent_simulation_id: UUID | None = Field(
        None, description="Optional ID of the parent simulation"
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: str = Field(..., description="Type of the simulation")
    status: str = Field(..., description="Current status of the simulation")
    campaign_id: str | None = Field(
        None, description="Optional ID of the associated campaign"
    )
    experiment_type_id: str | None = Field(
        None, description="Optional ID of the experiment type"
    )
    initialization_type: str = Field(
        ..., description="Initialization type for the simulation"
    )
    group_name: str | None = Field(
        None, description="Optional group name associated with the simulation"
    )

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID = Field(
        ..., description="ID of the machine used for the simulation"
    )
    simulation_start_date: datetime = Field(
        ..., description="Start date of the simulation"
    )
    simulation_end_date: datetime | None = Field(
        None, description="Optional end date of the simulation"
    )
    run_start_date: datetime | None = Field(
        None, description="Optional start date of the simulation run"
    )
    run_end_date: datetime | None = Field(
        None, description="Optional end date of the simulation run"
    )
    compiler: str | None = Field(
        None, description="Optional compiler used for the simulation"
    )

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = Field(
        None, description="Optional key features of the simulation"
    )
    known_issues: str | None = Field(
        None, description="Optional known issues with the simulation"
    )
    notes_markdown: str | None = Field(
        None, description="Optional additional notes in markdown format"
    )

    # Version control
    # ~~~~~~~~~~~~~~~
    git_repository_url: HttpUrl | None = Field(
        None, description="Optional Git repository URL"
    )
    git_branch: str | None = Field(
        None, description="Optional Git branch name associated with the simulation"
    )
    git_tag: str | None = Field(None, description="Optional Git tag for the simulation")
    git_commit_hash: str | None = Field(
        None, description="Optional Git commit hash associated with the simulation"
    )

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_at: datetime = Field(
        ..., description="Timestamp when the simulation was created"
    )
    created_by: str | None = Field(
        None, description="User who created the simulation, defined at creation time."
    )

    updated_at: datetime = Field(
        ..., description="Timestamp when the simulation was last updated"
    )
    last_updated_by: str | None = Field(
        None,
        description="User who last updated the simulation, defined at update time.",
    )

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: dict = Field(
        default_factory=dict,
        description="Optional extra metadata in flexible dictionary/JSON format",
    )

    # Relationships
    # ~~~~~~~~~~~~~~
    machine: MachineOut = Field(
        description="Machine on which the simulation was executed."
    )
    artifacts: list[ArtifactOut] = Field(
        default_factory=list,
        description="Optional list of artifacts associated with the simulation",
    )
    links: list[ExternalLinkOut] = Field(
        default_factory=list,
        description="Optional list of external links associated with the simulation",
    )

    # Computed fields
    # ~~~~~~~~~~~~~~~
    @computed_field(return_type=dict[str, list[ArtifactOut]])
    def grouped_artifacts(self) -> dict[str, list[ArtifactOut]]:
        return self._group_by_kind(self.artifacts)

    @computed_field(return_type=dict[str, list[ExternalLinkOut]])
    def grouped_links(self) -> dict[str, list[ExternalLinkOut]]:
        return self._group_by_kind(self.links)

    def _group_by_kind(self, items: list[Any]) -> dict[str, list[Any]]:
        grouped = defaultdict(list)

        for item in items:
            grouped[item.kind].append(item)

        return dict(grouped)
