from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
    model_validator,
)

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
ComputeType = Literal["cpu", "gpu"]


def _normalize_optional_label(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _normalize_optional_text(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return value


def _normalize_required_resource_value(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a non-empty string."
        raise ValueError(msg)

    stripped = value.strip()

    if not stripped:
        msg = f"{field_name} must be a non-empty string."
        raise ValueError(msg)

    return stripped


def _validate_unique_resources(items: list[Any], *, value_attr: str) -> list[Any]:
    seen: set[tuple[str, str]] = set()

    for item in items:
        value = getattr(item, value_attr)
        normalized_key = (item.kind.value, str(value))

        if normalized_key in seen:
            msg = f"Duplicate {item.kind.value} {value_attr} values are not allowed."
            raise ValueError(msg)

        seen.add(normalized_key)

    return items


class ExternalLinkCreate(CamelInBaseModel):
    """Schema for creating a new External Link."""

    kind: Annotated[
        ExternalLinkKind, Field(..., description="The type of the external link.")
    ]
    url: Annotated[HttpUrl, Field(..., description="The URL of the external link.")]
    label: Annotated[
        str | None, Field(None, description="An optional label for the external link.")
    ]

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _normalize_optional_label(value)


class ExternalLinkOut(CamelOutBaseModel):
    """Schema for representing an External Link object."""

    @model_validator(mode="before")
    @classmethod
    def populate_owner_type(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if "owner_type" in value or "ownerType" in value:
                return value

            if (
                value.get("simulation_id") is not None
                or value.get("simulationId") is not None
            ):
                return {**value, "owner_type": "simulation"}

            if value.get("case_id") is not None or value.get("caseId") is not None:
                return {**value, "owner_type": "case"}

            return value

        if getattr(value, "owner_type", None) is not None:
            return value

        simulation_id = getattr(value, "simulation_id", None)
        case_id = getattr(value, "case_id", None)
        owner_type = (
            "simulation"
            if simulation_id is not None
            else "case"
            if case_id is not None
            else None
        )

        if owner_type is None:
            return value

        return {
            "id": value.id,
            "kind": value.kind,
            "url": value.url,
            "label": value.label,
            "owner_type": owner_type,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
        }

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
    owner_type: Annotated[
        Literal["simulation", "case"],
        Field(
            ...,
            description=(
                "Owner of this link in SimBoard storage. Simulation-owned links are "
                "editable from simulation PATCH; case-owned links are read-only there."
            ),
        ),
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


class DiagnosticsLinkItem(CamelInBaseModel):
    """Schema for one diagnostic link to attach to a case."""

    name: Annotated[str, Field(..., description="Human-readable diagnostic label.")]
    url: Annotated[HttpUrl, Field(..., description="Diagnostic URL to attach.")]
    kind: Literal[ExternalLinkKind.DIAGNOSTIC] = Field(
        default=ExternalLinkKind.DIAGNOSTIC,
        description="Link type for diagnostics payloads. Must be 'diagnostic'.",
    )


class DiagnosticsLinkRequest(CamelInBaseModel):
    """Schema for linking diagnostics to a resolved case."""

    case_name: Annotated[
        str,
        Field(..., description="Exact case name used to resolve the target case."),
    ]
    machine: Annotated[
        str,
        Field(
            ...,
            description="Exact machine name used alongside case name to resolve the case.",
        ),
    ]
    hpc_username: Annotated[
        str,
        Field(
            ...,
            description="Exact HPC username used alongside case name and machine to resolve the case.",
        ),
    ]
    diagnostics: Annotated[
        list[DiagnosticsLinkItem],
        Field(
            ..., min_length=1, description="Diagnostic links to upsert for the case."
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

    @field_validator("uri", mode="before")
    @classmethod
    def normalize_uri(cls, value: Any) -> str:
        return _normalize_required_resource_value(value, field_name="uri")

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _normalize_optional_label(value)


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

    model_config = ConfigDict(extra="forbid")

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
                "Execution identifier for this run, derived from the timing-file "
                "LID (e.g. 1125772.260116-181605). Unique within its case."
            ),
        ),
    ]
    case_hash: Annotated[
        str | None,
        Field(
            None,
            description=(
                "Optional CASE_HASH parsed from env_case.xml. Used to group "
                "related executions or sub-cases within a case; not top-level "
                "case identity."
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
    compute_type: Annotated[
        ComputeType | None,
        Field(
            None,
            description="CPU or GPU execution type when encoded by the machine alias",
        ),
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

    @field_validator("artifacts")
    @classmethod
    def validate_unique_artifacts(
        cls, value: list[ArtifactCreate]
    ) -> list[ArtifactCreate]:
        return _validate_unique_resources(value, value_attr="uri")

    @field_validator("links")
    @classmethod
    def validate_unique_links(
        cls, value: list[ExternalLinkCreate]
    ) -> list[ExternalLinkCreate]:
        return _validate_unique_resources(value, value_attr="url")


class SimulationUpdate(CamelInBaseModel):
    """Schema for narrow v1 simulation metadata updates."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("simulation_type", "status", mode="before")
    @classmethod
    def reject_null_enum_updates(cls, value: Any) -> Any:
        if value is None:
            msg = "Field may be omitted for PATCH requests, but cannot be null."
            raise ValueError(msg)
        return value

    @field_validator("artifacts", "links", mode="before")
    @classmethod
    def reject_null_resource_updates(cls, value: Any) -> Any:
        if value is None:
            msg = "Field may be omitted for PATCH requests, but cannot be null."
            raise ValueError(msg)
        return value

    simulation_type: Annotated[
        SimulationType | None, Field(None, description="Type of the simulation")
    ]
    status: Annotated[
        SimulationStatus | None,
        Field(None, description="Current status of the simulation"),
    ]
    description: Annotated[
        str | None, Field(None, description="Optional description of the simulation")
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
    artifacts: Annotated[
        list[ArtifactCreate] | None,
        Field(
            None,
            description="Full replacement list of artifacts associated with the simulation",
        ),
    ]
    links: Annotated[
        list[ExternalLinkCreate] | None,
        Field(
            None,
            description="Full replacement list of external links associated with the simulation",
        ),
    ]

    @field_validator("artifacts")
    @classmethod
    def validate_update_artifacts(
        cls, value: list[ArtifactCreate] | None
    ) -> list[ArtifactCreate] | None:
        if value is None:
            return value
        return _validate_unique_resources(value, value_attr="uri")

    @field_validator("links")
    @classmethod
    def validate_update_links(
        cls, value: list[ExternalLinkCreate] | None
    ) -> list[ExternalLinkCreate] | None:
        if value is None:
            return value
        return _validate_unique_resources(value, value_attr="url")


class SimulationSummaryOut(CamelOutBaseModel):
    """Lightweight schema for simulation summaries nested inside case responses.

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
                "Execution identifier for this run, derived from the timing-file "
                "LID. Unique within its case."
            ),
        ),
    ]
    case_hash: Annotated[
        str | None,
        Field(
            None,
            description=(
                "Optional CASE_HASH used to group related executions or "
                "sub-cases within a case."
            ),
        ),
    ]
    compute_type: ComputeType | None = None
    status: Annotated[
        SimulationStatus, Field(..., description="Current status of the simulation")
    ]
    simulation_start_date: Annotated[
        datetime, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        datetime | None, Field(None, description="Optional end date of the simulation")
    ]


class SimulationSummaryCapabilitiesOut(CamelOutBaseModel):
    """Summary-generation capabilities available for this deployment."""

    llm_available: Annotated[
        bool,
        Field(
            ...,
            description="Whether this deployment can generate LLM-backed summaries.",
        ),
    ]
    auto_generate_deterministic_on_load: Annotated[
        bool,
        Field(
            ...,
            description="Whether deterministic summaries should auto-load on page open.",
        ),
    ]


class CaseListItemOut(CamelOutBaseModel):
    """Lightweight case row for paginated catalog views."""

    id: UUID
    name: str
    case_group: str | None = None
    machine_id: UUID
    machine_name: str
    hpc_username: str
    simulation_count: int
    created_at: datetime
    updated_at: datetime


class CasePageOut(CamelOutBaseModel):
    """Paginated case catalog response."""

    items: list[CaseListItemOut]
    total: int
    page: int
    page_size: int


class FilterOptionOut(CamelOutBaseModel):
    """Stable identifier and display label for a catalog filter option."""

    value: str
    label: str


class CaseFilterOptionsOut(CamelOutBaseModel):
    """Distinct scalar options supported by case catalog filters."""

    names: list[str]
    case_groups: list[str]
    hpc_usernames: list[str]
    machine_ids: list[UUID]
    machines: list[FilterOptionOut]
    statuses: list[SimulationStatus]
    simulation_types: list[SimulationType]
    campaigns: list[str]
    initialization_types: list[str]
    compilers: list[str]
    git_tags: list[str]
    created_by_ids: list[UUID]
    creators: list[FilterOptionOut]


class SimulationListItemOut(CamelOutBaseModel):
    """Scalar-only simulation row for paginated catalog views."""

    id: UUID
    case_id: UUID
    case_name: str
    case_group: str | None = None
    execution_id: str
    case_hash: str | None = None
    simulation_type: SimulationType
    status: SimulationStatus
    campaign: str | None = None
    experiment_type: str | None = None
    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str
    initialization_type: str
    simulation_start_date: datetime
    simulation_end_date: datetime | None = None
    run_start_date: datetime | None = None
    run_end_date: datetime | None = None
    compiler: str | None = None
    compute_type: ComputeType | None = None
    git_branch: str | None = None
    git_tag: str | None = None
    git_commit_hash: str | None = None
    machine_id: UUID
    machine_name: str
    hpc_username: str
    created_by: UUID | None = None
    last_updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SimulationPageOut(CamelOutBaseModel):
    """Paginated simulation catalog response."""

    items: list[SimulationListItemOut]
    total: int
    page: int
    page_size: int


class SimulationFilterOptionsOut(CamelOutBaseModel):
    """Distinct scalar options supported by simulation catalog filters."""

    case_names: list[str]
    case_groups: list[str]
    machine_ids: list[UUID]
    machines: list[FilterOptionOut]
    hpc_usernames: list[str]
    campaigns: list[str]
    experiment_types: list[str]
    compsets: list[str]
    grid_names: list[str]
    grid_resolutions: list[str]
    simulation_types: list[SimulationType]
    initialization_types: list[str]
    compilers: list[str]
    statuses: list[SimulationStatus]
    git_tags: list[str]
    created_by_ids: list[UUID]
    creators: list[FilterOptionOut]


class CatalogOverviewOut(CamelOutBaseModel):
    """Fixed-size homepage catalog summary."""

    total_cases: int
    total_simulations: int
    latest_submission: datetime | None = None
    machine_counts: dict[UUID, int]
    recent_cases: list[CaseListItemOut]


class CaseSummaryOut(CamelOutBaseModel):
    """Schema for representing a Case summary with nested simulation summaries."""

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
    links: Annotated[
        list[ExternalLinkOut],
        Field(
            default_factory=list,
            description="Optional list of external links associated with the case.",
        ),
    ]
    created_at: Annotated[
        datetime, Field(..., description="Timestamp when the case was created")
    ]
    updated_at: Annotated[
        datetime, Field(..., description="Timestamp when the case was last updated")
    ]


class CaseDetailOut(CaseSummaryOut):
    """Schema for representing full case details used by Case Details."""

    description: Annotated[
        str | None, Field(None, description="Optional shared description of the case")
    ]
    key_features: Annotated[
        str | None, Field(None, description="Optional shared key features of the case")
    ]
    known_issues: Annotated[
        str | None, Field(None, description="Optional shared known issues of the case")
    ]
    notes_markdown: Annotated[
        str | None,
        Field(
            None, description="Optional shared notes for the case in markdown format"
        ),
    ]


class CaseUpdate(CamelInBaseModel):
    """Schema for narrow v1 case metadata updates."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("links", mode="before")
    @classmethod
    def reject_null_link_updates(cls, value: Any) -> Any:
        if value is None:
            msg = "Field may be omitted for PATCH requests, but cannot be null."
            raise ValueError(msg)
        return value

    description: Annotated[
        str | None, Field(None, description="Optional shared description of the case")
    ]
    key_features: Annotated[
        str | None, Field(None, description="Optional shared key features of the case")
    ]
    known_issues: Annotated[
        str | None, Field(None, description="Optional shared known issues of the case")
    ]
    notes_markdown: Annotated[
        str | None,
        Field(
            None, description="Optional shared notes for the case in markdown format"
        ),
    ]
    links: Annotated[
        list[ExternalLinkCreate] | None,
        Field(
            None,
            description="Full replacement list of external links associated with the case",
        ),
    ]

    @field_validator(
        "description", "key_features", "known_issues", "notes_markdown", mode="before"
    )
    @classmethod
    def normalize_optional_metadata(cls, value: Any) -> Any:
        return _normalize_optional_text(value)

    @field_validator("links")
    @classmethod
    def validate_update_links(
        cls, value: list[ExternalLinkCreate] | None
    ) -> list[ExternalLinkCreate] | None:
        if value is None:
            return value
        return _validate_unique_resources(value, value_attr="url")


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
                "Execution identifier for this run, derived from the timing-file "
                "LID. Unique within its case."
            ),
        ),
    ]
    case_hash: Annotated[
        str | None,
        Field(
            None,
            description=(
                "Optional CASE_HASH parsed from env_case.xml. Used to group "
                "related executions or sub-cases within a case; not top-level "
                "case identity."
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
        UUID,
        Field(
            ...,
            description="ID of machine in selected case identity (derived from Case)",
        ),
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
    compute_type: Annotated[
        ComputeType | None,
        Field(
            None,
            description="CPU or GPU execution type when encoded by the machine alias",
        ),
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
            description="HPC username in selected case identity (derived from Case)",
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
    summary_capabilities: Annotated[
        SimulationSummaryCapabilitiesOut,
        Field(
            description=(
                "Deployment-level summary generation capabilities available to the UI."
            )
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
