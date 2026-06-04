from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter

from pydantic import ValidationError
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)

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
    SnapshotBudgetExceededError,
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
    "simulation.case_hash": lambda snapshot: snapshot.simulation.case_hash,
    "simulation.extra": lambda snapshot: snapshot.simulation.extra,
    "case.name": lambda snapshot: snapshot.case.name,
    "case.case_group": lambda snapshot: snapshot.case.case_group,
    "machine.name": lambda snapshot: snapshot.machine.name
    if snapshot.machine
    else None,
}

_INLINE_CITATION_RE = re.compile(
    r"\s*\[(?:simulation|case|machine|artifacts|links)[^\]]+\]"
)
_MULTISPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:])")


@dataclass(frozen=True)
class SummaryGenerationResult:
    summary: SimulationSummaryResponse
    fallback_reason: str | None
    llm_latency_ms: float
    attempted_provider: SummaryGenerationProvider | None
    attempted_model: str | None


def is_summary_llm_available() -> bool:
    """Return whether LLM-backed summaries are effectively available."""

    if not settings.assistant_llm_enabled:
        return False

    try:
        _resolve_llm_config()
    except ValueError:
        return False

    return True


async def generate_simulation_summary(
    simulation: Simulation,
    *,
    allow_llm: bool = True,
) -> SummaryGenerationResult:
    """
    Generates a simulation summary, attempting LLM generation if allowed and
    falling back to deterministic generation on failure.

    Parameters
    ----------
    simulation : Simulation
        The simulation for which to generate the summary
    allow_llm : bool, optional
        Whether to attempt LLM generation (default: True)

    Returns
    -------
    SummaryGenerationResult
        The result of the summary generation, including the summary response,
        any fallback reason, and LLM latency.
    """
    attempted_provider, attempted_model = _resolve_attempted_llm_metadata(
        allow_llm=allow_llm
    )

    try:
        snapshot = build_simulation_snapshot(simulation)
    except SnapshotBudgetExceededError as exc:
        if not allow_llm:
            return _build_deterministic_result(
                exc.snapshot,
                include_fallback_caveat=False,
                fallback_reason=None,
                attempted_provider=None,
                attempted_model=None,
            )

        return _build_deterministic_result(
            exc.snapshot,
            include_fallback_caveat=settings.assistant_llm_enabled,
            fallback_reason=str(exc)
            if settings.assistant_llm_enabled
            else "llm_disabled",
            attempted_provider=attempted_provider,
            attempted_model=attempted_model,
            fallback_used=settings.assistant_llm_enabled,
        )

    if not allow_llm:
        return _build_deterministic_result(
            snapshot,
            include_fallback_caveat=False,
            fallback_reason=None,
            attempted_provider=None,
            attempted_model=None,
        )

    if not settings.assistant_llm_enabled:
        return _build_deterministic_result(
            snapshot,
            include_fallback_caveat=False,
            fallback_reason="llm_disabled",
            attempted_provider=None,
            attempted_model=None,
        )

    try:
        config = _resolve_llm_config()
        generator = SummaryLLMGenerator(config)
    except ValueError as exc:
        return _build_deterministic_result(
            snapshot,
            include_fallback_caveat=True,
            fallback_reason=str(exc),
            attempted_provider=attempted_provider,
            attempted_model=attempted_model,
            fallback_used=True,
        )

    start = perf_counter()
    try:
        llm_content = await generator.generate(snapshot)
        llm_content = _fill_missing_llm_followups(llm_content, snapshot)
        validated = _validate_llm_content(llm_content, snapshot)

        return _build_llm_result(
            validated, config=config, llm_latency_ms=(perf_counter() - start) * 1000
        )
    except (ValidationError, ValueError) as exc:
        fallback_reason = getattr(exc, "args", ["llm_validation_failed"])[0]
    except Exception as exc:  # pragma: no cover - exercised via patched tests
        fallback_reason = _format_model_error(exc)

    return _build_deterministic_result(
        snapshot,
        include_fallback_caveat=True,
        fallback_reason=str(fallback_reason),
        llm_latency_ms=(perf_counter() - start) * 1000,
        attempted_provider=config.provider,
        attempted_model=config.model_name,
        fallback_used=True,
    )


def _resolve_attempted_llm_metadata(
    *,
    allow_llm: bool,
) -> tuple[SummaryGenerationProvider | None, str | None]:
    if not allow_llm or not settings.assistant_llm_enabled:
        return None, None

    provider = settings.assistant_llm_provider

    return provider, _configured_model_name(provider)


def _configured_model_name(provider: SummaryGenerationProvider) -> str | None:
    if provider == "livai":
        return settings.assistant_livai_model

    return settings.assistant_ollama_model


def _build_deterministic_result(
    snapshot: SimulationSnapshot,
    *,
    include_fallback_caveat: bool,
    fallback_reason: str | None,
    attempted_provider: SummaryGenerationProvider | None,
    attempted_model: str | None,
    fallback_used: bool = False,
    llm_latency_ms: float = 0.0,
) -> SummaryGenerationResult:
    summary = _build_deterministic_response(
        snapshot,
        include_fallback_caveat=include_fallback_caveat,
    )
    if fallback_used:
        summary = summary.model_copy(update={"fallback_used": True})

    result = SummaryGenerationResult(
        summary=summary,
        fallback_reason=fallback_reason,
        llm_latency_ms=llm_latency_ms,
        attempted_provider=attempted_provider,
        attempted_model=attempted_model,
    )

    return result


def _build_llm_result(
    validated: SimulationSummaryContent,
    *,
    config: AssistantLLMConfig,
    llm_latency_ms: float,
) -> SummaryGenerationResult:
    response = SimulationSummaryResponse(
        **validated.model_dump(),
        generation_mode="llm",
        fallback_used=False,
        generation_provider=config.provider,
        generation_model=config.model_name,
        trace_id="00000000-0000-0000-0000-000000000000",
    )

    return SummaryGenerationResult(
        summary=response,
        fallback_reason=None,
        llm_latency_ms=llm_latency_ms,
        attempted_provider=config.provider,
        attempted_model=config.model_name,
    )


def _resolve_llm_config() -> AssistantLLMConfig:
    provider = settings.assistant_llm_provider
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
            temperature=settings.assistant_llm_temperature,
            max_tokens=settings.assistant_llm_max_tokens,
            base_url=settings.assistant_livai_base_url,
        )

    if provider == "ollama":
        if (
            not settings.assistant_ollama_model
            or not settings.assistant_ollama_base_url
        ):
            raise ValueError("ollama_misconfigured")

        return AssistantLLMConfig(
            provider="ollama",
            model_name=settings.assistant_ollama_model,
            api_key=settings.assistant_ollama_api_key,
            timeout_seconds=settings.assistant_llm_timeout_seconds,
            temperature=settings.assistant_llm_temperature,
            max_tokens=settings.assistant_llm_max_tokens,
            base_url=settings.assistant_ollama_base_url,
        )

    raise ValueError("unsupported_provider")


def _standardize_citations(
    citations: list[SummaryCitationOut],
    snapshot: SimulationSnapshot,
) -> list[SummaryCitationOut]:
    normalized: list[SummaryCitationOut] = []

    for citation in citations:
        canonical_path = _canonicalize_citation_path(
            citation.path,
            citation.source_type,
        )

        if not _snapshot_has_citation_path(snapshot, canonical_path):
            raise ValueError(f"missing_citation_path:{canonical_path}")

        entry = get_citation_entry(canonical_path)

        normalized.append(
            SummaryCitationOut(
                source_type=entry.source_type,
                path=canonical_path,
                label=entry.label,
            )
        )

    return normalized


def _canonicalize_citation_path(path: str, source_type: str | None = None) -> str:
    normalized = path.strip()

    if normalized in VALID_CITATION_PATHS:
        return normalized

    matches = [
        candidate
        for candidate in VALID_CITATION_PATHS
        if candidate.endswith(f".{normalized}")
    ]

    if source_type is not None:
        typed_matches = [
            candidate
            for candidate in matches
            if get_citation_entry(candidate).source_type == source_type
        ]

        if len(typed_matches) == 1:
            return typed_matches[0]

    if len(matches) == 1:
        return matches[0]

    raise ValueError(f"invalid_citation_path:{path}")


def _snapshot_has_citation_path(snapshot: SimulationSnapshot, path: str) -> bool:
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
    normalized_answer = _normalize_llm_answer(content.answer)

    if not normalized_answer:
        raise ValueError("empty_answer")
    if not content.citations:
        raise ValueError("missing_citations")
    if not content.limitations:
        raise ValueError("missing_limitations")
    if not content.suggested_followups:
        raise ValueError("missing_followups")

    return content.model_copy(
        update={
            "answer": normalized_answer,
            "citations": _standardize_citations(content.citations, snapshot),
            "caveats": _merge_unique_strings(
                snapshot.snapshot_caveats, content.caveats
            ),
            "limitations": _merge_unique_strings(content.limitations, LLM_LIMITATIONS),
        }
    )


def _normalize_llm_answer(answer: str) -> str:
    cleaned = _INLINE_CITATION_RE.sub("", answer)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned).strip()
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)

    return cleaned


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


def _fill_missing_llm_followups(
    content: SimulationSummaryContent,
    snapshot: SimulationSnapshot,
) -> SimulationSummaryContent:
    if content.suggested_followups:
        return content

    fallback_summary = build_simulation_summary(snapshot)

    return content.model_copy(
        update={"suggested_followups": fallback_summary.suggested_followups}
    )


def _format_model_error(exc: Exception) -> str:
    if isinstance(exc, ModelHTTPError):
        body = exc.body

        if body is not None and not isinstance(body, str):
            body = json.dumps(body, sort_keys=True)
        return _trim_fallback_reason(
            f"{exc.__class__.__name__}: status_code={exc.status_code}; body={body}"
        )

    if isinstance(exc, (ModelAPIError, UnexpectedModelBehavior)):
        return _trim_fallback_reason(f"{exc.__class__.__name__}: {exc}")

    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__

    return _trim_fallback_reason(f"{exc.__class__.__name__}: {message}")


def _trim_fallback_reason(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value

    return f"{value[: limit - 3]}..."
