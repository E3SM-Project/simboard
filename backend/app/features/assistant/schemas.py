from typing import Literal
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import CamelOutBaseModel


class SummaryCitationOut(CamelOutBaseModel):
    """Metadata citation for a deterministic simulation summary."""

    source_type: Literal[
        "simulation_field",
        "case_field",
        "machine_field",
        "artifact",
        "external_link",
    ] = Field(..., description="Kind of SimBoard record referenced by the summary.")
    path: str = Field(
        ...,
        description="Stable field path or related-record selector used by the summary.",
    )
    label: str = Field(..., description="Human-readable label for the cited source.")


class SimulationSummaryResponse(CamelOutBaseModel):
    """Structured response returned by the deterministic summary endpoint."""

    answer: str = Field(
        ..., description="Deterministic summary prose for the simulation."
    )
    citations: list[SummaryCitationOut] = Field(
        default_factory=list,
        description="Metadata citations backing claims in the answer.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions used by the formatter.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Missing-data or weak-signal warnings for the summary.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Known limits of this deterministic summary implementation.",
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="Non-agentic follow-up checks derived from available metadata.",
    )
    trace_id: UUID = Field(..., description="Trace ID for request review and logs.")
