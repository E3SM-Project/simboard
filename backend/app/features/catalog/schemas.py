from collections import defaultdict
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
)

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel
from app.features.catalog.enums import (
    ArtifactKind,
    ExecutionStatus,
    ExperimentType,
    ExternalLinkKind,
    SimulationType,
)
from app.features.machine.schemas import MachineOut
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


class ExecutionExternalLinkOut(CamelOutBaseModel):
    """Canonical external-link contract for execution and case owners."""

    id: UUID
    kind: ExternalLinkKind
    url: HttpUrl
    label: str | None = None
    owner_type: Annotated[
        Literal["execution", "case"],
        Field(
            description=(
                "Owner of this link. Execution-owned links are editable from execution "
                "PATCH; case-owned links are read-only there."
            )
        ),
    ]
    created_at: datetime
    updated_at: datetime


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


class ExecutionCreate(CamelInBaseModel):
    """Schema for creating a new execution."""

    model_config = ConfigDict(extra="forbid")

    # Configuration
    # --------------
    case_id: Annotated[
        UUID, Field(..., description="ID of the Case this execution belongs to")
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
        str | None, Field(None, description="Optional description of the execution")
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
        ExecutionStatus, Field(..., description="Current status of the execution")
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
        date, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        date | None, Field(None, description="Optional end date of the simulation")
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
            None, description="Optional Git branch name associated with the execution"
        ),
    ]
    git_tag: Annotated[
        str | None, Field(None, description="Optional Git tag for the execution")
    ]
    git_commit_hash: Annotated[
        str | None,
        Field(
            None, description="Optional Git commit hash associated with the execution"
        ),
    ]

    # Provenance & submission
    # -----------------------
    created_by: Annotated[
        UUID | None,
        Field(
            None,
            description="User ID who created the execution, defined at creation time.",
        ),
    ]
    last_updated_by: Annotated[
        UUID | None,
        Field(
            None,
            description="User ID who last updated the execution, defined at update time.",
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
            description="Optional list of artifacts associated with the execution",
        ),
    ]
    links: Annotated[
        list[ExternalLinkCreate],
        Field(
            default_factory=list,
            description="Optional list of external links associated with the execution",
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


class ExecutionUpdate(CamelInBaseModel):
    """Schema for narrow v1 execution metadata updates."""

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
        ExecutionStatus | None,
        Field(None, description="Current status of the execution"),
    ]
    description: Annotated[
        str | None, Field(None, description="Optional description of the execution")
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
            description="Full replacement list of artifacts associated with the execution",
        ),
    ]
    links: Annotated[
        list[ExternalLinkCreate] | None,
        Field(
            None,
            description="Full replacement list of external links associated with the execution",
        ),
    ]
    edit_reason: Annotated[
        str | None,
        Field(None, description="Optional reason recorded with metadata changes"),
    ]

    @field_validator("edit_reason", mode="before")
    @classmethod
    def normalize_edit_reason(cls, value: Any) -> Any:
        return _normalize_optional_text(value)

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


class ExecutionSummaryOut(CamelOutBaseModel):
    """Lightweight schema for execution summaries nested inside case responses.

    Only includes the fields needed for case-level overview — avoids loading
    heavy relationships (machine, artifacts, links, user objects).
    """

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the execution.")
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
        ExecutionStatus, Field(..., description="Current status of the execution")
    ]
    simulation_start_date: Annotated[
        date, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        date | None, Field(None, description="Optional end date of the simulation")
    ]


class ExecutionSummaryCapabilitiesOut(CamelOutBaseModel):
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


class LatestExecutionSummaryOut(CamelOutBaseModel):
    """Run-derived summary of the deterministically latest completed execution."""

    execution_id: str
    status: ExecutionStatus
    run_start_date: datetime | None = None
    run_end_date: datetime | None = None


class CaseListItemOut(CamelOutBaseModel):
    """Lightweight case row for paginated catalog views."""

    id: UUID
    name: str
    case_group: str | None = None
    machine_id: UUID
    machine_name: str
    hpc_username: str
    execution_count: int
    created_at: datetime
    updated_at: datetime
    latest_execution: LatestExecutionSummaryOut | None = None


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
    statuses: list[ExecutionStatus]
    simulation_types: list[SimulationType]
    campaigns: list[str]
    initialization_types: list[str]
    compilers: list[str]
    git_tags: list[str]
    created_by_ids: list[UUID]
    creators: list[FilterOptionOut]


class ExecutionListItemOut(CamelOutBaseModel):
    """Scalar-only execution row for paginated catalog views."""

    id: UUID
    case_id: UUID
    case_name: str
    case_group: str | None = None
    execution_id: str
    case_hash: str | None = None
    simulation_type: SimulationType
    status: ExecutionStatus
    campaign: str | None = None
    experiment_type: str | None = None
    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str
    initialization_type: str
    simulation_start_date: date
    simulation_end_date: date | None = None
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


class ExecutionPageOut(CamelOutBaseModel):
    """Paginated execution catalog response."""

    items: list[ExecutionListItemOut]
    total: int
    page: int
    page_size: int


class ExecutionFilterOptionsOut(CamelOutBaseModel):
    """Distinct scalar options supported by execution catalog filters."""

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
    statuses: list[ExecutionStatus]
    git_tags: list[str]
    created_by_ids: list[UUID]
    creators: list[FilterOptionOut]


class CatalogOverviewOut(CamelOutBaseModel):
    """Fixed-size homepage catalog summary."""

    total_cases: int
    total_executions: int
    latest_submission: datetime | None = None
    machine_counts: dict[UUID, int]
    recent_cases: list[CaseListItemOut]


class CaseSummaryOut(CamelOutBaseModel):
    """Schema for representing a case summary with nested execution summaries."""

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
    executions: Annotated[
        list[ExecutionSummaryOut],
        Field(
            default_factory=list,
            description="Executions belonging to this case.",
        ),
    ]
    machine_names: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Unique machine names represented across this case's executions.",
        ),
    ]
    hpc_usernames: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Unique HPC usernames represented across this case's executions.",
        ),
    ]
    links: Annotated[
        list[ExecutionExternalLinkOut],
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
    edit_reason: Annotated[
        str | None,
        Field(None, description="Optional reason recorded with metadata changes"),
    ]

    @field_validator("edit_reason", mode="before")
    @classmethod
    def normalize_edit_reason(cls, value: Any) -> Any:
        return _normalize_optional_text(value)

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


class MetadataChangeOut(CamelOutBaseModel):
    """Append-only record for one managed metadata field change."""

    id: UUID
    entity_type: Literal["case", "execution"]
    entity_id: UUID
    field_name: str
    old_value: Any
    new_value: Any
    editor_id: UUID
    editor: UserPreview
    changed_at: datetime
    reason: str | None = None


class MetadataHistoryPageOut(CamelOutBaseModel):
    """Paginated metadata history, with page size measured in change events."""

    items: list[MetadataChangeOut]
    total: int
    page: int
    page_size: int


class ExecutionOut(CamelOutBaseModel):
    """Schema for representing an execution with related entities."""

    id: Annotated[
        UUID, Field(..., description="The unique identifier of the execution.")
    ]

    # Configuration
    # --------------
    case_id: Annotated[
        UUID, Field(..., description="ID of the Case this execution belongs to")
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
        str | None, Field(None, description="Optional description of the execution")
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
        ExecutionStatus, Field(..., description="Current status of the execution")
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
        date, Field(..., description="Start date of the simulation")
    ]
    simulation_end_date: Annotated[
        date | None, Field(None, description="Optional end date of the simulation")
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
            None, description="Optional Git branch name associated with the execution"
        ),
    ]
    git_tag: Annotated[
        str | None, Field(None, description="Optional Git tag for the execution")
    ]
    git_commit_hash: Annotated[
        str | None,
        Field(
            None, description="Optional Git commit hash associated with the execution"
        ),
    ]

    # Provenance & submission
    # -----------------------
    created_at: Annotated[
        datetime, Field(..., description="Timestamp when the execution was created")
    ]
    created_by: Annotated[
        UUID | None, Field(description="User ID who created the execution.")
    ]
    created_by_user: Annotated[
        UserPreview | None,
        Field(description="Full user info of who created the execution."),
    ]

    updated_at: Annotated[
        datetime,
        Field(..., description="Timestamp when the execution was last updated"),
    ]
    last_updated_by: Annotated[
        UUID | None, Field(description="User ID who last updated the execution.")
    ]
    last_updated_by_user: Annotated[
        UserPreview | None,
        Field(description="Full user info of who last updated the execution."),
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
        ExecutionSummaryCapabilitiesOut,
        Field(
            description=(
                "Deployment-level summary generation capabilities available to the UI."
            )
        ),
    ]

    # Relationships
    # --------------
    machine: Annotated[
        MachineOut, Field(description="Machine on which the execution ran.")
    ]
    artifacts: Annotated[
        list[ArtifactOut],
        Field(
            default_factory=list,
            description="Optional list of artifacts associated with the execution",
        ),
    ]
    links: Annotated[
        list[ExecutionExternalLinkOut],
        Field(
            default_factory=list,
            description="Optional list of external links associated with the execution",
        ),
    ]

    # Computed fields
    # ---------------
    @computed_field(return_type=dict[str, list[ArtifactOut]])
    def grouped_artifacts(self) -> dict[str, list[ArtifactOut]]:
        return self._group_by_kind(self.artifacts)

    @computed_field(return_type=dict[str, list[ExecutionExternalLinkOut]])
    def grouped_links(self) -> dict[str, list[ExecutionExternalLinkOut]]:
        return self._group_by_kind(self.links)

    def _group_by_kind(self, items: list[Any]) -> dict[str, list[Any]]:
        grouped = defaultdict(list)

        for item in items:
            grouped[item.kind].append(item)

        return dict(grouped)
