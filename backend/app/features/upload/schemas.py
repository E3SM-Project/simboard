from pydantic import BaseModel, Field

from app.features.simulation.schemas import SimulationCreate


class IngestArchiveRequest(BaseModel):
    """Request payload for ingesting an archive and persisting simulations."""

    archive_path: str = Field(..., description="Path to the archive file")
    output_dir: str = Field(..., description="Directory for extracted files")


class IngestArchiveResponse(BaseModel):
    """Response payload for ingesting and persisting simulations."""

    created_count: int
    skipped_count: int
    simulations: list[SimulationCreate]
