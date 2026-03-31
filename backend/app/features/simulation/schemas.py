from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, HttpUrl, computed_field

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel
from app.features.machine.schemas import MachineOut
from app.features.simulation.enums import (
    ArtifactKind,
    ExperimentType,
    ExternalLinkKind,
    SimulationStatus,
    SimulationType,
)
from app.features.user.schemas import UserPreview

KNOWN_EXPERIMENT_TYPES = {e.value for e in ExperimentType}


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
        str,
        Field(
            ..., description="The URI or filesystem path where the artifact is located."
        ),
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
        str,
        Field(
            ..., description="The URI or filesystem path where the artifact is located."
        ),
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
    case_id: Annotated[
        UUID, Field(..., description="ID of the Case this simulation belongs to")
    ]
    execution_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Unique identifier for this execution, derived from the "
                "timing-file LID (e.g. 1125772.260116-181605)"
            ),
        ),
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

    # Model setup/context
    # -------------------
    simulation_type: Annotated[
        SimulationType, Field(..., description="Type of the simulation")
    ]
    status: Annotated[
        SimulationStatus, Field(..., description="Current status of the simulation")
    ]
    campaign: Annotated[
        str | None,
        Field(
            None, description="Campaign or run grouping (e.g. historical, amip, tuning)"
        ),
    ]
    experiment_type: Annotated[
        ExperimentType | str | None,
        Field(
            None,
            description=(
                "High-level experiment category (e.g. historical, amip, piControl). "
                "Often aligned with CMIP experiment identifiers."
            ),
        ),
    ]
    initialization_type: Annotated[
        str, Field(..., description="Initialization type for the simulation")
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
        UUID | None,
        Field(
            None,
            description="User ID who created the simulation, defined at creation time.",
        ),
    ]
    last_updated_by: Annotated[
        UUID | None,
        Field(
            None,
            description="User ID who last updated the simulation, defined at update time.",
        ),
    ]
    hpc_username: Annotated[
        str | None,
        Field(
            None,
            description="HPC username for provenance (trusted, informational only)",
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
    run_config_deltas: Annotated[
        dict[str, Any] | None,
        Field(
            None,
            description=(
                "Configuration differences between this simulation and the "
                "canonical baseline for the same case. None for canonical "
                "simulations or when no differences exist."
            ),
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


class SimulationSummaryOut(CamelOutBaseModel):
    """Lightweight schema for simulation summaries nested inside CaseOut.

    Only includes the fields needed for case-level overview — avoids loading
    heavy relationships (machine, artifacts, links, user objects).
    """

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the simulation.")
    ]
    execution_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Unique identifier for this execution, derived from the timing-file LID"
            ),
        ),
    ]
    status: Annotated[
        SimulationStatus, Field(..., description="Current status of the simulation")
    ]
    is_canonical: Annotated[
        bool,
        Field(
            ...,
            description="Whether this simulation is the canonical baseline for its case",
        ),
    ]
    change_count: Annotated[
        int,
        Field(
            ...,
            description=(
                "Number of configuration differences vs the canonical baseline. "
                "0 for canonical simulations."
            ),
        ),
    ]
    simulation_start_date: Annotated[
        datetime, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        datetime | None, Field(None, description="Optional end date of the simulation")
    ]


class CaseOut(CamelOutBaseModel):
    """Schema for representing a Case with nested simulation summaries."""

    id: Annotated[UUID, Field(..., description="The unique identifier of the case.")]
    name: Annotated[str, Field(..., description="The case name.")]
    case_group: Annotated[
        str | None,
        Field(
            None,
            description=(
                "Optional case group (CASE_GROUP from env_case.xml). "
                "Groups related cases (e.g. ensemble members) together."
            ),
        ),
    ]
    canonical_simulation_id: Annotated[
        UUID | None,
        Field(None, description="ID of the canonical simulation for this case."),
    ]
    simulations: Annotated[
        list[SimulationSummaryOut],
        Field(
            default_factory=list,
            description="Simulation executions belonging to this case.",
        ),
    ]
    machine_names: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Unique machine names represented across this case's simulations.",
        ),
    ]
    hpc_usernames: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Unique HPC usernames represented across this case's simulations.",
        ),
    ]
    created_at: Annotated[
        datetime, Field(..., description="Timestamp when the case was created")
    ]
    updated_at: Annotated[
        datetime, Field(..., description="Timestamp when the case was last updated")
    ]


class SimulationOut(CamelOutBaseModel):
    """Schema for representing a Simulation with related entities."""

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the simulation.")
    ]

    # Configuration
    # --------------
    case_id: Annotated[
        UUID, Field(..., description="ID of the Case this simulation belongs to")
    ]
    case_name: Annotated[
        str, Field(..., description="Case name (derived from the associated Case)")
    ]
    case_group: Annotated[
        str | None,
        Field(
            None,
            description=(
                "Case group (CASE_GROUP from env_case.xml, derived from Case). "
                "Groups related cases together."
            ),
        ),
    ]
    execution_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Unique identifier for this execution, derived from the timing-file LID"
            ),
        ),
    ]
    is_canonical: Annotated[
        bool,
        Field(
            ...,
            description="Whether this simulation is the canonical baseline for its case",
        ),
    ]
    change_count: Annotated[
        int,
        Field(
            ...,
            description=(
                "Number of configuration differences vs the canonical baseline. "
                "0 for canonical simulations."
            ),
        ),
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

    # Model setup/context
    # -------------------
    simulation_type: Annotated[
        SimulationType, Field(..., description="Type of the simulation")
    ]
    status: Annotated[
        SimulationStatus, Field(..., description="Current status of the simulation")
    ]
    campaign: Annotated[
        str | None,
        Field(
            None, description="Campaign or run grouping (e.g. historical, amip, tuning)"
        ),
    ]
    experiment_type: Annotated[
        ExperimentType | str | None,
        Field(
            None,
            description=(
                "High-level experiment category (e.g. historical, amip, piControl). "
                "Often aligned with CMIP experiment identifiers."
            ),
        ),
    ]
    initialization_type: Annotated[
        str, Field(..., description="Initialization type for the simulation")
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
        UUID | None, Field(description="User ID who created the simulation.")
    ]
    created_by_user: Annotated[
        UserPreview | None,
        Field(description="Full user info of who created the simulation."),
    ]

    updated_at: Annotated[
        datetime,
        Field(..., description="Timestamp when the simulation was last updated"),
    ]
    last_updated_by: Annotated[
        UUID | None, Field(description="User ID who last updated the simulation.")
    ]
    last_updated_by_user: Annotated[
        UserPreview | None,
        Field(description="Full user info of who last updated the simulation."),
    ]
    hpc_username: Annotated[
        str | None,
        Field(
            None,
            description="HPC username for provenance (trusted, informational only)",
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
    run_config_deltas: Annotated[
        dict[str, Any] | None,
        Field(
            None,
            description=(
                "Configuration differences between this simulation and the "
                "canonical baseline for the same case. None for canonical "
                "simulations or when no differences exist."
            ),
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
