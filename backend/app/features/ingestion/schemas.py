from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features.ingestion.enums import (
    ExecutionDiscoveryOutcome,
    IngestionSourceType,
    IngestionStatus,
)


class IngestionSimulationSummary(BaseModel):
    """Lightweight summary of a persisted simulation created by ingestion."""

    id: Annotated[UUID, Field(..., description="ID of the created simulation")]
    case_id: Annotated[UUID, Field(..., description="ID of the associated case")]
    case_name: Annotated[str, Field(..., description="Name of the associated case")]
    execution_id: Annotated[
        str, Field(..., description="Execution identifier for the created simulation")
    ]


class IngestFromPathRequest(BaseModel):
    """
    Request payload for ingesting an archive from a path and persisting
    simulations.
    """

    archive_path: Annotated[str, Field(..., description="Path to the archive file")]
    machine_name: Annotated[
        str,
        Field(..., description="Name of the machine associated with the simulations"),
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
        Field(..., description="Name of the machine associated with the simulations"),
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
    """Response payload for ingesting and persisting simulations."""

    created_count: Annotated[
        int, Field(..., description="Number of new simulations created")
    ]
    duplicate_count: Annotated[
        int, Field(..., description="Number of duplicate simulations detected")
    ]
    simulations: Annotated[
        list[IngestionSimulationSummary],
        Field(..., description="List of created simulation summaries"),
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
    """One immutable execution discovery result."""

    case_identity: Annotated[str, Field(..., min_length=1)]
    execution_id: Annotated[str, Field(..., min_length=1)]
    outcome: ExecutionDiscoveryOutcome

    @field_validator("case_identity", "execution_id")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identifier must not be blank")
        return normalized


class ExecutionDiscoveryResultsRequest(BaseModel):
    """Batch of immutable discovery results for one machine."""

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
    """Persistence summary for a discovery-result batch."""

    inserted_count: int
    existing_count: int


class ArchiveCheckpointEntry(BaseModel):
    """One completed immutable archive snapshot."""

    archive_month: Annotated[str, Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    snapshot_name: Annotated[
        str,
        Field(
            ...,
            pattern=(r"^performance_archive_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$"),
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
            description="Normalized case identity to immutable discovery results",
        ),
    ]


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
        UUID, Field(..., description="ID of the machine used for the simulation")
    ]
    triggered_by: Annotated[
        UUID, Field(..., description="User ID or process that triggered the ingestion")
    ]
    status: Annotated[
        IngestionStatus, Field(..., description="Status of the ingestion event")
    ]
    created_count: Annotated[
        int, Field(..., description="Number of new simulations created")
    ]
    duplicate_count: Annotated[
        int, Field(..., description="Number of duplicate simulations detected")
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
        UUID, Field(..., description="ID of the machine used for the simulation")
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
        int, Field(..., description="Number of new simulations created")
    ]
    duplicateCount: Annotated[
        int, Field(..., description="Number of duplicate simulations detected")
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
