from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import AnyUrl, Field, HttpUrl, computed_field

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel
from app.features.machine.schemas import MachineOut


class ArtifactKind(str, Enum):
    """Enumeration of possible artifact types."""

    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESS_SCRIPT = "postprocessing_script"


class ExternalLinkKind(str, Enum):
    """Enumeration of possible external link types."""

    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


class ExternalLinkCreate(CamelInBaseModel):
    """Schema for creating a new External Link."""

    kind: Annotated[
        ExternalLinkKind, Field(..., description="The type of the external link.")
    ]
    url: Annotated[HttpUrl, Field(..., description="The URL of the external link.")]
    label: Annotated[
        str | None, Field(None, description="An optional label for the external link.")
    ]


class ExternalLinkOut(CamelOutBaseModel):
    """Schema for representing an External Link object."""

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the external link.")
    ]
    kind: Annotated[
        ExternalLinkKind, Field(..., description="The type of the external link.")
    ]
    url: Annotated[HttpUrl, Field(..., description="The URL of the external link.")]
    label: Annotated[
        str | None, Field(None, description="An optional label for the external link.")
    ]
    created_at: Annotated[
        datetime,
        Field(..., description="The timestamp when the external link was created."),
    ]
    updated_at: Annotated[
        datetime,
        Field(
            ..., description="The timestamp when the external link was last updated."
        ),
    ]


class ArtifactCreate(CamelInBaseModel):
    """Schema for creating a new Artifact."""

    kind: Annotated[ArtifactKind, Field(..., description="The type of the artifact.")]
    uri: Annotated[
        AnyUrl, Field(..., description="The URI where the artifact is located.")
    ]
    label: Annotated[
        str | None, Field(None, description="An optional label for the artifact.")
    ]


class ArtifactOut(CamelOutBaseModel):
    """Schema for representing an Artifact object."""

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the artifact.")
    ]
    kind: Annotated[ArtifactKind, Field(..., description="The type of the artifact.")]
    uri: Annotated[
        AnyUrl, Field(..., description="The URI where the artifact is located.")
    ]
    label: Annotated[
        str | None, Field(None, description="An optional label for the artifact.")
    ]
    created_at: Annotated[
        datetime, Field(..., description="The timestamp when the artifact was created.")
    ]
    updated_at: Annotated[
        datetime,
        Field(..., description="The timestamp when the artifact was last updated."),
    ]


class SimulationCreate(CamelInBaseModel):
    """Schema for creating a new Simulation."""

    # Configuration
    # --------------
    name: Annotated[str, Field(..., description="Name of the simulation")]
    case_name: Annotated[
        str, Field(..., description="Case name associated with the simulation")
    ]
    description: Annotated[
        str | None, Field(None, description="Optional description of the simulation")
    ]
    compset: Annotated[
        str, Field(..., description="Component set used in the simulation")
    ]
    compset_alias: Annotated[str, Field(..., description="Alias for the component set")]
    grid_name: Annotated[
        str, Field(..., description="Grid name used in the simulation")
    ]
    grid_resolution: Annotated[
        str, Field(..., description="Grid resolution used in the simulation")
    ]
    parent_simulation_id: Annotated[
        UUID | None, Field(None, description="Optional ID of the parent simulation")
    ]

    # Model setup/context
    # -------------------
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: Annotated[str, Field(..., description="Type of the simulation")]
    status: Annotated[str, Field(..., description="Current status of the simulation")]
    campaign_id: Annotated[
        str | None, Field(None, description="Optional ID of the associated campaign")
    ]
    experiment_type_id: Annotated[
        str | None, Field(None, description="Optional ID of the experiment type")
    ]
    initialization_type: Annotated[
        str, Field(..., description="Initialization type for the simulation")
    ]
    group_name: Annotated[
        str | None,
        Field(None, description="Optional group name associated with the simulation"),
    ]

    # Model timeline
    # --------------
    machine_id: Annotated[
        UUID, Field(..., description="ID of the machine used for the simulation")
    ]
    simulation_start_date: Annotated[
        datetime, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        datetime | None, Field(None, description="Optional end date of the simulation")
    ]
    run_start_date: Annotated[
        datetime | None,
        Field(None, description="Optional start date of the simulation run"),
    ]
    run_end_date: Annotated[
        datetime | None,
        Field(None, description="Optional end date of the simulation run"),
    ]
    compiler: Annotated[
        str | None, Field(None, description="Optional compiler used for the simulation")
    ]

    # Metadata & audit
    # -----------------
    key_features: Annotated[
        str | None, Field(None, description="Optional key features of the simulation")
    ]
    known_issues: Annotated[
        str | None, Field(None, description="Optional known issues with the simulation")
    ]
    notes_markdown: Annotated[
        str | None,
        Field(None, description="Optional additional notes in markdown format"),
    ]

    # Version control
    # ---------------
    git_repository_url: Annotated[
        HttpUrl | None, Field(None, description="Optional Git repository URL")
    ]
    git_branch: Annotated[
        str | None,
        Field(
            None, description="Optional Git branch name associated with the simulation"
        ),
    ]
    git_tag: Annotated[
        str | None, Field(None, description="Optional Git tag for the simulation")
    ]
    git_commit_hash: Annotated[
        str | None,
        Field(
            None, description="Optional Git commit hash associated with the simulation"
        ),
    ]

    # Provenance & submission
    # -----------------------
    created_by: Annotated[
        str | None,
        Field(
            None,
            description="User who created the simulation, defined at creation time.",
        ),
    ]
    last_updated_by: Annotated[
        str | None,
        Field(
            None,
            description="User who last updated the simulation, defined at update time.",
        ),
    ]

    # Miscellaneous
    # -----------------
    extra: Annotated[
        dict,
        Field(
            default_factory=dict,
            description="Optional extra metadata in flexible dictionary/JSON format",
        ),
    ]

    # Relationships
    # --------------
    artifacts: Annotated[
        list[ArtifactCreate],
        Field(
            default_factory=list,
            description="Optional list of artifacts associated with the simulation",
        ),
    ]
    links: Annotated[
        list[ExternalLinkCreate],
        Field(
            default_factory=list,
            description="Optional list of external links associated with the simulation",
        ),
    ]


class SimulationOut(CamelOutBaseModel):
    """Schema for representing a Simulation with related entities."""

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the simulation.")
    ]

    # Configuration
    # --------------
    name: Annotated[str, Field(..., description="Name of the simulation")]
    case_name: Annotated[
        str, Field(..., description="Case name associated with the simulation")
    ]
    description: Annotated[
        str | None, Field(None, description="Optional description of the simulation")
    ]
    compset: Annotated[
        str, Field(..., description="Component set used in the simulation")
    ]
    compset_alias: Annotated[str, Field(..., description="Alias for the component set")]
    grid_name: Annotated[
        str, Field(..., description="Grid name used in the simulation")
    ]
    grid_resolution: Annotated[
        str, Field(..., description="Grid resolution used in the simulation")
    ]
    parent_simulation_id: Annotated[
        UUID | None, Field(None, description="Optional ID of the parent simulation")
    ]

    # Model setup/context
    # -------------------
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: Annotated[str, Field(..., description="Type of the simulation")]
    status: Annotated[str, Field(..., description="Current status of the simulation")]
    campaign_id: Annotated[
        str | None, Field(None, description="Optional ID of the associated campaign")
    ]
    experiment_type_id: Annotated[
        str | None, Field(None, description="Optional ID of the experiment type")
    ]
    initialization_type: Annotated[
        str, Field(..., description="Initialization type for the simulation")
    ]
    group_name: Annotated[
        str | None,
        Field(None, description="Optional group name associated with the simulation"),
    ]

    # Model timeline
    # --------------
    machine_id: Annotated[
        UUID, Field(..., description="ID of the machine used for the simulation")
    ]
    simulation_start_date: Annotated[
        datetime, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        datetime | None, Field(None, description="Optional end date of the simulation")
    ]
    run_start_date: Annotated[
        datetime | None,
        Field(None, description="Optional start date of the simulation run"),
    ]
    run_end_date: Annotated[
        datetime | None,
        Field(None, description="Optional end date of the simulation run"),
    ]
    compiler: Annotated[
        str | None, Field(None, description="Optional compiler used for the simulation")
    ]

    # Metadata & audit
    # -----------------
    key_features: Annotated[
        str | None, Field(None, description="Optional key features of the simulation")
    ]
    known_issues: Annotated[
        str | None, Field(None, description="Optional known issues with the simulation")
    ]
    notes_markdown: Annotated[
        str | None,
        Field(None, description="Optional additional notes in markdown format"),
    ]

    # Version control
    # ---------------
    git_repository_url: Annotated[
        HttpUrl | None, Field(None, description="Optional Git repository URL")
    ]
    git_branch: Annotated[
        str | None,
        Field(
            None, description="Optional Git branch name associated with the simulation"
        ),
    ]
    git_tag: Annotated[
        str | None, Field(None, description="Optional Git tag for the simulation")
    ]
    git_commit_hash: Annotated[
        str | None,
        Field(
            None, description="Optional Git commit hash associated with the simulation"
        ),
    ]

    # Provenance & submission
    # -----------------------
    created_at: Annotated[
        datetime, Field(..., description="Timestamp when the simulation was created")
    ]
    created_by: Annotated[
        str | None,
        Field(
            None,
            description="User who created the simulation, defined at creation time.",
        ),
    ]
    updated_at: Annotated[
        datetime,
        Field(..., description="Timestamp when the simulation was last updated"),
    ]
    last_updated_by: Annotated[
        str | None,
        Field(
            None,
            description="User who last updated the simulation, defined at update time.",
        ),
    ]

    # Miscellaneous
    # -----------------
    extra: Annotated[
        dict,
        Field(
            default_factory=dict,
            description="Optional extra metadata in flexible dictionary/JSON format",
        ),
    ]

    # Relationships
    # --------------
    machine: Annotated[
        MachineOut, Field(description="Machine on which the simulation was executed.")
    ]
    artifacts: Annotated[
        list[ArtifactOut],
        Field(
            default_factory=list,
            description="Optional list of artifacts associated with the simulation",
        ),
    ]
    links: Annotated[
        list[ExternalLinkOut],
        Field(
            default_factory=list,
            description="Optional list of external links associated with the simulation",
        ),
    ]

    # Computed fields
    # ---------------
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
