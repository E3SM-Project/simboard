from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.features.catalog.enums import SourceDirectoryKind
from app.features.ingestion.enums import (
    ExecutionDiscoveryOutcome,
    IngestionSourceType,
    IngestionStatus,
    ScheduledJobFailureReason,
    ScheduledJobHealth,
    ScheduledJobRunStatus,
    ScheduledJobUploadFailureCategory,
)
from app.features.ingestion.models import FAILURE_MESSAGE_MAX_LENGTH

# PACE producers use either a bare timestamp or an opaque machine/project prefix.
ARCHIVE_SNAPSHOT_NAME_PATTERN = (
    r"^performance_archive_(?:[A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)+_)?"
    r"\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$"
)
SCHEDULED_JOB_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,99}$"
# One year keeps derived deadlines within datetime range.
SCHEDULED_JOB_MAX_THRESHOLD_MINUTES = 525_600
ScheduledJobScanMode = Literal["staging", "archive", "diagnostics"]
UPLOAD_FAILURE_CASES_MAX = 50
UPLOAD_FAILURE_MESSAGE_MAX_LENGTH = 200
# Failure counts are keyed by HTTP status, or "network" for errors and timeouts.
UploadFailureKey = Annotated[str, Field(pattern=r"^(?:network|[1-5]\d\d)$")]


class IngestionExecutionSummary(BaseModel):
    """Lightweight summary of a persisted execution created by ingestion."""

    id: Annotated[UUID, Field(..., description="ID of the created execution")]
    case_id: Annotated[UUID, Field(..., description="ID of the associated case")]
    case_name: Annotated[str, Field(..., description="Name of the associated case")]
    machine_name: Annotated[
        str, Field(..., description="Name of the associated machine")
    ]
    hpc_username: Annotated[
        str, Field(..., description="HPC username associated with the case")
    ]
    execution_id: Annotated[
        str, Field(..., description="Execution identifier for the created execution")
    ]


class SourceDirectoryObservation(BaseModel):
    """Observed paths and explicit catalog identity for one execution."""

    case_name: Annotated[str, Field(min_length=1)]
    hpc_username: Annotated[str, Field(min_length=1)]
    execution_id: Annotated[str, Field(min_length=1)]
    kind: SourceDirectoryKind
    case_path: Annotated[str, Field(min_length=1)]
    execution_path: Annotated[str, Field(min_length=1)]

    @field_validator("case_name", "hpc_username", "execution_id")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Identity must not be blank")
        return value

    @field_validator("case_path", "execution_path")
    @classmethod
    def validate_observed_path(cls, value: str) -> str:
        if not value.startswith("/") or "\x00" in value:
            raise ValueError("Source directory must be an absolute path")
        return value


class SourceDirectoriesRequest(BaseModel):
    machine_name: Annotated[str, Field(min_length=1)]
    dry_run: bool = False
    directories: Annotated[
        list[SourceDirectoryObservation], Field(min_length=1, max_length=500)
    ]


class SourceDirectoriesResponse(BaseModel):
    recorded_count: int
    unresolved: list[SourceDirectoryObservation] = Field(default_factory=list)


class IngestFromPathRequest(BaseModel):
    """
    Request payload for ingesting an archive from a path and persisting
    executions.
    """

    archive_path: Annotated[str, Field(..., description="Path to the archive file")]
    source_directories: list[SourceDirectoryObservation] = Field(default_factory=list)
    selected_execution_ids: Annotated[
        list[str] | None,
        Field(
            default=None,
            min_length=1,
            description="Only parse these execution directory names; omitted means all",
        ),
    ] = None
    machine_name: Annotated[
        str,
        Field(..., description="Name of the machine associated with the executions"),
    ]
    hpc_username: Annotated[
        str | None,
        Field(
            default=None,
            description="HPC username for provenance (trusted, informational only)",
        ),
    ] = None
    processed_execution_ids: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Execution IDs already discovered for this case path by the caller",
        ),
    ] = None


class IngestFromHpcUploadRequest(BaseModel):
    """Request payload for automated HPC archive upload ingestion."""

    machine_name: Annotated[
        str,
        Field(..., description="Name of the machine associated with the executions"),
    ]
    case_path: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description="Stable case path used as the dedupe identity",
        ),
    ]
    processed_execution_ids: Annotated[
        list[str],
        Field(
            ...,
            min_length=1,
            description="Full discovered execution IDs for this case path",
        ),
    ]
    hpc_username: Annotated[
        str | None,
        Field(
            default=None,
            description="HPC username for provenance (trusted, informational only)",
        ),
    ] = None


class IngestionResponse(BaseModel):
    """Response payload for ingesting and persisting executions."""

    created_count: Annotated[
        int, Field(..., description="Number of new executions created")
    ]
    duplicate_count: Annotated[
        int, Field(..., description="Number of duplicate executions detected")
    ]
    executions: Annotated[
        list[IngestionExecutionSummary],
        Field(..., description="List of created execution summaries"),
    ]
    errors: Annotated[
        list[dict[str, str]],
        Field(..., description="List of errors encountered during ingestion"),
    ]


class IngestionStateCase(BaseModel):
    """Known execution state for one ingested case path."""

    processed_execution_ids: Annotated[
        list[str],
        Field(
            ..., description="Sorted execution IDs already persisted for this case path"
        ),
    ]
    fingerprint: Annotated[
        str,
        Field(..., description="Deterministic fingerprint of processed execution IDs"),
    ]


class ExecutionDiscoveryResultEntry(BaseModel):
    """One execution discovery result; rejections can change after revalidation."""

    case_identity: Annotated[str, Field(..., min_length=1)]
    execution_id: Annotated[str, Field(..., min_length=1)]
    outcome: ExecutionDiscoveryOutcome
    errors: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("case_identity", "execution_id")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identifier must not be blank")
        return normalized


class ExecutionDiscoveryResultsRequest(BaseModel):
    """Batch of discovery results for one machine."""

    machine_name: Annotated[str, Field(..., min_length=1)]
    results: Annotated[list[ExecutionDiscoveryResultEntry], Field(..., min_length=1)]

    @field_validator("machine_name")
    @classmethod
    def strip_machine_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Machine name must not be blank")
        return normalized

    @model_validator(mode="after")
    def reject_conflicting_results(self) -> "ExecutionDiscoveryResultsRequest":
        outcomes: dict[tuple[str, str], ExecutionDiscoveryOutcome] = {}
        for result in self.results:
            identity = (result.case_identity, result.execution_id)
            prior = outcomes.setdefault(identity, result.outcome)
            if prior != result.outcome:
                raise ValueError(
                    "Same case identity and execution ID cannot have different outcomes"
                )
        return self


class ExecutionDiscoveryResultsResponse(BaseModel):
    """Persistence summary; existing_count includes refreshed rejected rows."""

    inserted_count: int
    existing_count: int


class ArchiveCheckpointEntry(BaseModel):
    """One completed immutable archive snapshot."""

    archive_month: Annotated[str, Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    snapshot_name: Annotated[
        str,
        Field(
            ...,
            pattern=ARCHIVE_SNAPSHOT_NAME_PATTERN,
        ),
    ]


class ArchiveCheckpointsRequest(BaseModel):
    """Batch of completed archive snapshots for one machine and archive."""

    machine_name: Annotated[str, Field(..., min_length=1)]
    archive_name: Annotated[str, Field(..., min_length=1)]
    snapshots: Annotated[list[ArchiveCheckpointEntry], Field(..., min_length=1)]

    @field_validator("machine_name", "archive_name")
    @classmethod
    def strip_checkpoint_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Checkpoint identity must not be blank")
        return normalized


class ArchiveCheckpointsResponse(BaseModel):
    """Persistence summary for an archive-checkpoint batch."""

    inserted_count: int
    existing_count: int


class ArchiveCheckpointListResponse(BaseModel):
    """Completed immutable snapshots for one machine and archive."""

    machine_name: str
    archive_name: str
    snapshots: list[ArchiveCheckpointEntry]


class IngestionStateResponse(BaseModel):
    """Database-backed ingestion state for one machine."""

    machine_name: Annotated[
        str,
        Field(..., description="Canonical machine name used for this state lookup"),
    ]
    cases: Annotated[
        dict[str, IngestionStateCase],
        Field(..., description="Case path to processed execution state mapping"),
    ]
    discovery_results: Annotated[
        dict[str, list[ExecutionDiscoveryResultEntry]],
        Field(
            default_factory=dict,
            description="Normalized case identity to discovery results",
        ),
    ]


class IngestionSummaryRow(BaseModel):
    day: date
    machine: str
    case_id: UUID
    case_name: str
    hpc_username: str
    new_executions: int


class IngestionSummaryTotals(BaseModel):
    new_executions: int = 0
    distinct_cases: int = 0


class IngestionSummaryDayTotals(IngestionSummaryTotals):
    day: date


class IngestionSummaryMachineTotals(IngestionSummaryDayTotals):
    machine: str


class IngestionSummaryResponse(BaseModel):
    rows: list[IngestionSummaryRow] = Field(default_factory=list)
    daily_machine_totals: list[IngestionSummaryMachineTotals] = Field(
        default_factory=list
    )
    daily_totals: list[IngestionSummaryDayTotals] = Field(default_factory=list)
    totals: IngestionSummaryTotals = Field(default_factory=IngestionSummaryTotals)


class IngestionCreate(BaseModel):
    """Schema for creating an ingestion audit record."""

    source_type: Annotated[
        IngestionSourceType,
        Field(..., description="Type of the ingestion source (e.g., file, API)"),
    ]
    source_reference: Annotated[
        str,
        Field(
            ..., description="Reference to the ingestion source (e.g., file path, URL)"
        ),
    ]
    machine_id: Annotated[
        UUID, Field(..., description="ID of the machine used for the execution")
    ]
    triggered_by: Annotated[
        UUID, Field(..., description="User ID or process that triggered the ingestion")
    ]
    status: Annotated[
        IngestionStatus, Field(..., description="Status of the ingestion event")
    ]
    created_count: Annotated[
        int, Field(..., description="Number of new executions created")
    ]
    duplicate_count: Annotated[
        int, Field(..., description="Number of duplicate executions detected")
    ]
    error_count: Annotated[
        int, Field(..., description="Number of errors encountered during ingestion")
    ]
    archive_sha256: Annotated[
        str | None,
        Field(
            default=None,
            description="SHA256 hash of the ingested archive, if available",
        ),
    ]
    processed_execution_ids: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Execution IDs the caller considers processed for this ingestion",
        ),
    ] = None


class IngestionRead(BaseModel):
    """Audit record representation for an ingestion event."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[
        UUID, Field(..., description="Unique identifier for the ingestion record")
    ]
    sourceType: Annotated[
        IngestionSourceType,
        Field(..., description="Type of the ingestion source (e.g., file, API)"),
    ]
    sourceReference: Annotated[
        str,
        Field(
            ..., description="Reference to the ingestion source (e.g., file path, URL)"
        ),
    ]
    machine_id: Annotated[
        UUID, Field(..., description="ID of the machine used for the execution")
    ]
    triggeredBy: Annotated[
        UUID, Field(..., description="User ID or process that triggered the ingestion")
    ]
    createdAt: Annotated[
        datetime, Field(..., description="Timestamp when the ingestion was created")
    ]
    status: Annotated[
        IngestionStatus, Field(..., description="Status of the ingestion event")
    ]
    createdCount: Annotated[
        int, Field(..., description="Number of new executions created")
    ]
    duplicateCount: Annotated[
        int, Field(..., description="Number of duplicate executions detected")
    ]
    errorCount: Annotated[
        int, Field(..., description="Number of errors encountered during ingestion")
    ]
    archiveSha256: Annotated[
        str | None,
        Field(
            default=None,
            description="SHA256 hash of the ingested archive, if available",
        ),
    ]


class ScheduledJobRegister(BaseModel):
    """Admin registration of one scheduled job and its health thresholds."""

    machine_name: str
    scan_mode: ScheduledJobScanMode
    service_account_email: str
    max_silence_minutes: Annotated[
        int, Field(gt=0, le=SCHEDULED_JOB_MAX_THRESHOLD_MINUTES)
    ]
    max_duration_minutes: Annotated[
        int, Field(gt=0, le=SCHEDULED_JOB_MAX_THRESHOLD_MINUTES)
    ]


class ScheduledJobReport(BaseModel):
    """Job identity sent with every report; it registers an unknown job."""

    machine_name: str
    scan_mode: ScheduledJobScanMode


class ScheduledJobRunStart(ScheduledJobReport):
    started_at: AwareDatetime


class ScheduledJobFailure(BaseModel):
    reason: ScheduledJobFailureReason
    message: Annotated[str, Field(max_length=FAILURE_MESSAGE_MAX_LENGTH)]
    status_code: Annotated[int, Field(ge=100, le=599)] | None = None
    transient: bool | None = None


class ScheduledJobUploadFailure(BaseModel):
    """One case upload that failed after retries."""

    case_path: Annotated[str, Field(max_length=4096)]
    # None for network errors and timeouts.
    status_code: Annotated[int, Field(ge=100, le=599)] | None
    attempts: Annotated[int, Field(ge=0)]
    message: Annotated[str, Field(max_length=UPLOAD_FAILURE_MESSAGE_MAX_LENGTH)]


class ScheduledJobUploadFailures(BaseModel):
    """Complete failure counts with a bounded list of failed cases."""

    counts: dict[UploadFailureKey, Annotated[int, Field(gt=0)]]
    cases: Annotated[
        list[ScheduledJobUploadFailure], Field(max_length=UPLOAD_FAILURE_CASES_MAX)
    ]
    truncated: bool


class ScheduledJobRunFinish(ScheduledJobReport):
    """Finish report; the start time lets a lost start report be recovered."""

    started_at: AwareDatetime
    finished_at: AwareDatetime
    exit_code: Annotated[int, Field(ge=0, le=255)]
    failure: ScheduledJobFailure | None = None
    upload_failures: ScheduledJobUploadFailures | None = None

    @model_validator(mode="after")
    def _require_failure_for_nonzero_exit(self) -> "ScheduledJobRunFinish":
        if (self.exit_code == 0) != (self.failure is None):
            raise ValueError("A failure is required exactly when exit_code is nonzero.")

        return self


class ScheduledJobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ScheduledJobRunStatus
    started_at: datetime
    finished_at: datetime | None
    reported_at: datetime
    finish_reported_at: datetime | None
    exit_code: int | None
    failure_reason: ScheduledJobFailureReason | None
    failure_message: str | None
    failure_status_code: int | None
    failure_transient: bool | None
    upload_failures: ScheduledJobUploadFailures | None


class ScheduledJobRead(BaseModel):
    id: str
    machine_name: str
    scan_mode: str
    max_silence_minutes: int
    max_duration_minutes: int


class ScheduledJobHealthRead(ScheduledJobRead):
    """Latest completed outcome is kept separate from active-run state."""

    health: ScheduledJobHealth
    last_reported_at: datetime | None
    latest_completed_run: ScheduledJobRunRead | None
    active_run: ScheduledJobRunRead | None
    active_run_count: int


class ScheduledJobUploadFailureDailyCount(BaseModel):
    """Failed case uploads on one UTC day, by machine and category."""

    day: date
    machine_name: str
    category: ScheduledJobUploadFailureCategory
    count: int


class ScheduledJobHealthResponse(BaseModel):
    jobs: list[ScheduledJobHealthRead] = Field(default_factory=list)
    upload_failure_daily_counts: list[ScheduledJobUploadFailureDailyCount] = Field(
        default_factory=list
    )
