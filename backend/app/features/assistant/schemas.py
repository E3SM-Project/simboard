from typing import Literal
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import CamelOutBaseModel


class SummaryCitationOut(CamelOutBaseModel):
    """Metadata citation for a simulation summary."""

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


SummaryGenerationMode = Literal["llm", "deterministic"]
SummaryGenerationProvider = Literal["livai", "ollama"]


class SimulationSummaryContent(CamelOutBaseModel):
    """Structured simulation summary content."""

    answer: str = Field(
        ..., description="Metadata-grounded summary prose for the simulation."
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


class SimulationSummaryResponse(SimulationSummaryContent):
    """Structured response returned by the simulation summary endpoint."""

    generation_mode: SummaryGenerationMode = Field(
        ...,
        description="Whether the summary came from the LLM path or deterministic fallback.",
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether this summary came from an attempted LLM generation that fell back to deterministic output.",
    )
    generation_provider: SummaryGenerationProvider | None = Field(
        ...,
        description="Provider name when LLM generation succeeds; otherwise null.",
    )
    generation_model: str | None = Field(
        ...,
        description="Configured provider model when LLM generation succeeds; otherwise null.",
    )
    trace_id: UUID = Field(..., description="Trace ID for request review and logs.")
