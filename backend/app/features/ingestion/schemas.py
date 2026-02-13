from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.features.simulation.schemas import SimulationCreate


class IngestionStatus(str, Enum):
    """Status values for ingestion audit records."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestArchiveRequest(BaseModel):
    """Request payload for ingesting an archive and persisting simulations."""

    archive_path: str = Field(..., description="Path to the archive file")
    output_dir: str = Field(..., description="Directory for extracted files")


class IngestArchiveResponse(BaseModel):
    """Response payload for ingesting and persisting simulations."""

    created_count: int
    duplicate_count: int
    simulations: list[SimulationCreate]
    errors: list[dict[str, str]]


class IngestionCreate(BaseModel):
    """Schema for creating an ingestion audit record."""

    source_type: str
    source_reference: str
    triggered_by: UUID
    status: str
    created_count: int
    duplicate_count: int
    error_count: int
    archive_sha256: str | None = None


class IngestionRead(BaseModel):
    """Audit record representation for an ingestion event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sourceType: str
    sourceReference: str
    triggeredBy: UUID
    createdAt: datetime
    status: str
    createdCount: int
    duplicateCount: int
    errorCount: int
    archiveSha256: str | None = None
