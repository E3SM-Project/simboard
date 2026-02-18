from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.simulation.schemas import SimulationCreate


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


class IngestionResponse(BaseModel):
    """Response payload for ingesting and persisting simulations."""

    created_count: Annotated[
        int, Field(..., description="Number of new simulations created")
    ]
    duplicate_count: Annotated[
        int, Field(..., description="Number of duplicate simulations detected")
    ]
    simulations: Annotated[
        list[SimulationCreate],
        Field(..., description="List of created simulation objects"),
    ]
    errors: Annotated[
        list[dict[str, str]],
        Field(..., description="List of errors encountered during ingestion"),
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
