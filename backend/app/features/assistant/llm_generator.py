from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from httpx import AsyncClient
from openai import AsyncOpenAI
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.features.assistant.registry import CITATION_REGISTRY
from app.features.assistant.schemas import (
    SimulationSummaryContent,
    SummaryGenerationProvider,
)
from app.features.assistant.snapshot import SimulationSnapshot

SUMMARY_SYSTEM_PROMPT = """
You generate structured SimBoard simulation summaries from provided metadata only.

Rules:
- Use only snapshot metadata supplied in prompt.
- Do not use external knowledge, retrieval, or unstated assumptions.
- Do not interpret diagnostics or scientific results beyond what metadata explicitly says.
- If metadata is missing or truncated, say so in caveats.
- Keep claims grounded in citations.
- Use only allowed citation paths and source types provided in prompt.
- Every `citations.path` value must exactly match one allowed path string.
- Never shorten or rewrite citation paths. For example, use `simulation.status`, `case.name`, and `machine.name`, not `status` or `name`.
- If you cannot cite a claim with an exact allowed path, omit that claim instead of inventing a citation path.
- Produce concise, factual output for all structured fields.
- Return every structured field required by schema, even when brief.
- `suggested_followups` must contain at least one concrete item.
- Keep `answer` to 2-4 short sentences and under 120 words.
- Prioritize the few most decision-useful facts: status, case/campaign, configuration, machine, and notable provenance or timing only when material.
- Do not enumerate every available field.
- Do not repeat raw citation paths or add inline bracketed citations such as `[simulation.status]` inside the answer text.
- Put evidence only in the structured `citations` field, not inline in prose.
- Prefer natural language over field-by-field narration.
""".strip()


@dataclass(frozen=True)
class AssistantLLMConfig:
    provider: SummaryGenerationProvider
    model_name: str
    api_key: SecretStr | None
    timeout_seconds: float
    temperature: float
    max_tokens: int
    base_url: str | None = None


class SummaryLLMGenerator:
    def __init__(self, config: AssistantLLMConfig) -> None:
        self.config = config

    async def generate(self, snapshot: SimulationSnapshot) -> SimulationSummaryContent:
        async with AsyncClient(timeout=self.config.timeout_seconds) as http_client:
            model = self._build_model(http_client)
            agent = Agent(
                model,
                output_type=self._build_output_type(),
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                model_settings=self._build_model_settings(),
            )
            result = await agent.run(self._build_user_prompt(snapshot))
            return result.output

    def _build_model(self, http_client: AsyncClient) -> OpenAIChatModel:
        api_key = (
            self.config.api_key.get_secret_value()
            if self.config.api_key is not None
            else None
        )
        provider_kwargs = {
            "api_key": api_key,
            "base_url": self._resolve_base_url(),
            "http_client": http_client,
        }
        if self.config.provider == "ollama":
            provider_kwargs = {
                "openai_client": AsyncOpenAI(
                    **provider_kwargs,
                    max_retries=0,
                    timeout=self.config.timeout_seconds,
                    _enforce_credentials=False,
                )
            }
        return OpenAIChatModel(
            self.config.model_name,
            provider=OpenAIProvider(**provider_kwargs),
        )

    def _resolve_base_url(self) -> str | None:
        if self.config.provider != "ollama" or self.config.base_url is None:
            return self.config.base_url

        parsed = urlparse(self.config.base_url)
        if parsed.path not in {"", "/"}:
            return self.config.base_url
        return f"{self.config.base_url.rstrip('/')}/v1"

    def _build_model_settings(self) -> ModelSettings | None:
        settings: ModelSettings = {
            "max_tokens": self.config.max_tokens,
        }
        if not (
            self.config.provider == "livai"
            and self.config.model_name.startswith("gpt-5")
        ):
            settings["temperature"] = self.config.temperature
        return settings or None

    def _build_output_type(
        self,
    ) -> type[SimulationSummaryContent] | PromptedOutput[SimulationSummaryContent]:
        if self.config.provider == "ollama":
            return PromptedOutput(SimulationSummaryContent)
        return SimulationSummaryContent

    def _build_user_prompt(self, snapshot: SimulationSnapshot) -> str:
        allowed_citations = "\n".join(
            f"- {path} ({entry.source_type})"
            for path, entry in sorted(CITATION_REGISTRY.items())
        )
        snapshot_json = snapshot.model_dump_json(indent=2, exclude_none=True)
        return (
            "Simulation metadata snapshot:\n"
            f"{snapshot_json}\n\n"
            "Allowed citation paths:\n"
            f"{allowed_citations}\n"
        )
