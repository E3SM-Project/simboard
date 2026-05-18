from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from pydantic import ValidationError

from app.core.config import settings
from app.features.assistant.llm_generator import AssistantLLMConfig, SummaryLLMGenerator
from app.features.assistant.registry import VALID_CITATION_PATHS, get_citation_entry
from app.features.assistant.schemas import (
    SimulationSummaryContent,
    SimulationSummaryResponse,
    SummaryCitationOut,
    SummaryGenerationProvider,
)
from app.features.assistant.service import (
    LLM_LIMITATIONS,
    build_simulation_summary,
)
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    build_simulation_snapshot,
)
from app.features.simulation.models import Simulation

_SNAPSHOT_PATH_ACCESSORS = {
    "simulation.id": lambda snapshot: snapshot.simulation.id,
    "simulation.execution_id": lambda snapshot: snapshot.simulation.execution_id,
    "simulation.description": lambda snapshot: snapshot.simulation.description,
    "simulation.compset": lambda snapshot: snapshot.simulation.compset,
    "simulation.compset_alias": lambda snapshot: snapshot.simulation.compset_alias,
    "simulation.grid_name": lambda snapshot: snapshot.simulation.grid_name,
    "simulation.grid_resolution": lambda snapshot: snapshot.simulation.grid_resolution,
    "simulation.simulation_type": lambda snapshot: snapshot.simulation.simulation_type,
    "simulation.status": lambda snapshot: snapshot.simulation.status,
    "simulation.campaign": lambda snapshot: snapshot.simulation.campaign,
    "simulation.experiment_type": lambda snapshot: snapshot.simulation.experiment_type,
    "simulation.initialization_type": lambda snapshot: snapshot.simulation.initialization_type,
    "simulation.simulation_start_date": lambda snapshot: snapshot.simulation.simulation_start_date,
    "simulation.simulation_end_date": lambda snapshot: snapshot.simulation.simulation_end_date,
    "simulation.run_start_date": lambda snapshot: snapshot.simulation.run_start_date,
    "simulation.run_end_date": lambda snapshot: snapshot.simulation.run_end_date,
    "simulation.compiler": lambda snapshot: snapshot.simulation.compiler,
    "simulation.key_features": lambda snapshot: snapshot.simulation.key_features,
    "simulation.known_issues": lambda snapshot: snapshot.simulation.known_issues,
    "simulation.notes_markdown": lambda snapshot: snapshot.simulation.notes_markdown,
    "simulation.git_repository_url": lambda snapshot: snapshot.simulation.git_repository_url,
    "simulation.git_branch": lambda snapshot: snapshot.simulation.git_branch,
    "simulation.git_tag": lambda snapshot: snapshot.simulation.git_tag,
    "simulation.git_commit_hash": lambda snapshot: snapshot.simulation.git_commit_hash,
    "simulation.extra": lambda snapshot: snapshot.simulation.extra,
    "simulation.run_config_deltas": lambda snapshot: snapshot.simulation.run_config_deltas,
    "case.name": lambda snapshot: snapshot.case.name,
    "case.case_group": lambda snapshot: snapshot.case.case_group,
    "case.reference_simulation_id": lambda snapshot: snapshot.case.reference_simulation_id,
    "machine.name": lambda snapshot: snapshot.machine.name
    if snapshot.machine
    else None,
}


@dataclass(frozen=True)
class SummaryGenerationResult:
    summary: SimulationSummaryResponse
    fallback_reason: str | None
    llm_latency_ms: float
    attempted_provider: SummaryGenerationProvider | None
    attempted_model: str | None


def _standardize_citations(
    citations: list[SummaryCitationOut],
    snapshot: SimulationSnapshot,
) -> list[SummaryCitationOut]:
    normalized: list[SummaryCitationOut] = []
    for citation in citations:
        if citation.path not in VALID_CITATION_PATHS:
            raise ValueError(f"invalid_citation_path:{citation.path}")
        if not snapshot_has_citation_path(snapshot, citation.path):
            raise ValueError(f"missing_citation_path:{citation.path}")
        entry = get_citation_entry(citation.path)
        normalized.append(
            SummaryCitationOut(
                source_type=entry.source_type,
                path=citation.path,
                label=entry.label,
            )
        )
    return normalized


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _validate_llm_content(
    content: SimulationSummaryContent,
    snapshot: SimulationSnapshot,
) -> SimulationSummaryContent:
    if not content.answer.strip():
        raise ValueError("empty_answer")
    if not content.citations:
        raise ValueError("missing_citations")
    if not content.limitations:
        raise ValueError("missing_limitations")
    if not content.suggested_followups:
        raise ValueError("missing_followups")

    return content.model_copy(
        update={
            "citations": _standardize_citations(content.citations, snapshot),
            "caveats": _merge_unique_strings(
                snapshot.snapshot_caveats, content.caveats
            ),
            "limitations": _merge_unique_strings(content.limitations, LLM_LIMITATIONS),
        }
    )


def _build_deterministic_response(
    snapshot: SimulationSnapshot,
    *,
    include_fallback_caveat: bool,
) -> SimulationSummaryResponse:
    base = build_simulation_summary(
        snapshot,
        include_fallback_caveat=include_fallback_caveat,
    )
    return base.model_copy(
        update={
            "generation_mode": "deterministic",
            "generation_provider": None,
            "generation_model": None,
        }
    )


def _resolve_llm_config() -> AssistantLLMConfig:
    provider = settings.assistant_llm_provider
    if provider == "openai":
        if (
            settings.assistant_openai_api_key is None
            or not settings.assistant_openai_model
        ):
            raise ValueError("openai_misconfigured")
        return AssistantLLMConfig(
            provider="openai",
            model_name=settings.assistant_openai_model,
            api_key=settings.assistant_openai_api_key,
            timeout_seconds=settings.assistant_llm_timeout_seconds,
        )

    if provider == "anthropic":
        if (
            settings.assistant_anthropic_api_key is None
            or not settings.assistant_anthropic_model
        ):
            raise ValueError("anthropic_misconfigured")
        return AssistantLLMConfig(
            provider="anthropic",
            model_name=settings.assistant_anthropic_model,
            api_key=settings.assistant_anthropic_api_key,
            timeout_seconds=settings.assistant_llm_timeout_seconds,
        )

    if provider == "livai":
        if (
            settings.assistant_livai_api_key is None
            or not settings.assistant_livai_model
            or not settings.assistant_livai_base_url
        ):
            raise ValueError("livai_misconfigured")
        return AssistantLLMConfig(
            provider="livai",
            model_name=settings.assistant_livai_model,
            api_key=settings.assistant_livai_api_key,
            timeout_seconds=settings.assistant_llm_timeout_seconds,
            base_url=settings.assistant_livai_base_url,
        )

    raise ValueError("unsupported_provider")


def _configured_model_name(provider: SummaryGenerationProvider) -> str | None:
    if provider == "openai":
        return settings.assistant_openai_model
    if provider == "anthropic":
        return settings.assistant_anthropic_model
    return settings.assistant_livai_model


async def generate_simulation_summary(
    simulation: Simulation,
) -> SummaryGenerationResult:
    snapshot = build_simulation_snapshot(simulation)

    if not settings.assistant_llm_enabled:
        return SummaryGenerationResult(
            summary=_build_deterministic_response(
                snapshot,
                include_fallback_caveat=False,
            ),
            fallback_reason="llm_disabled",
            llm_latency_ms=0.0,
            attempted_provider=None,
            attempted_model=None,
        )

    attempted_provider: SummaryGenerationProvider | None = (
        settings.assistant_llm_provider
    )
    attempted_model: str | None = _configured_model_name(
        settings.assistant_llm_provider
    )

    try:
        config = _resolve_llm_config()
        attempted_provider = config.provider
        attempted_model = config.model_name
        generator = SummaryLLMGenerator(config)
    except ValueError as exc:
        return SummaryGenerationResult(
            summary=_build_deterministic_response(
                snapshot,
                include_fallback_caveat=True,
            ),
            fallback_reason=str(exc),
            llm_latency_ms=0.0,
            attempted_provider=attempted_provider,
            attempted_model=attempted_model,
        )

    start = perf_counter()
    try:
        llm_content = await generator.generate(snapshot)
        validated = _validate_llm_content(llm_content, snapshot)
        response = SimulationSummaryResponse(
            **validated.model_dump(),
            generation_mode="llm",
            generation_provider=config.provider,
            generation_model=config.model_name,
            trace_id="00000000-0000-0000-0000-000000000000",
        )
        return SummaryGenerationResult(
            summary=response,
            fallback_reason=None,
            llm_latency_ms=(perf_counter() - start) * 1000,
            attempted_provider=config.provider,
            attempted_model=config.model_name,
        )
    except (ValidationError, ValueError) as exc:
        fallback_reason = getattr(exc, "args", ["llm_validation_failed"])[0]
    except Exception as exc:  # pragma: no cover - exercised via patched tests
        fallback_reason = exc.__class__.__name__

    return SummaryGenerationResult(
        summary=_build_deterministic_response(
            snapshot,
            include_fallback_caveat=True,
        ),
        fallback_reason=str(fallback_reason),
        llm_latency_ms=(perf_counter() - start) * 1000,
        attempted_provider=config.provider,
        attempted_model=config.model_name,
    )


def snapshot_has_citation_path(snapshot: SimulationSnapshot, path: str) -> bool:
    accessor = _SNAPSHOT_PATH_ACCESSORS.get(path)
    if accessor is not None:
        return bool(accessor(snapshot))
    if path.startswith("artifacts[kind="):
        kind = path[len("artifacts[kind=") : -1]
        return any(item.kind == kind for item in snapshot.artifacts)
    if path.startswith("links[kind="):
        kind = path[len("links[kind=") : -1]
        return any(item.kind == kind for item in snapshot.links)
    return False
