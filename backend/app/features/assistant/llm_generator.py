from __future__ import annotations

from dataclasses import dataclass

from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
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
- Produce concise, factual output for all structured fields.
""".strip()


@dataclass(frozen=True)
class AssistantLLMConfig:
    provider: SummaryGenerationProvider
    model_name: str
    api_key: SecretStr
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
                output_type=SimulationSummaryContent,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                model_settings=self._build_model_settings(),
            )
            result = await agent.run(self._build_user_prompt(snapshot))
            return result.output

    def _build_model(
        self, http_client: AsyncClient
    ) -> OpenAIChatModel | AnthropicModel:
        api_key = self.config.api_key.get_secret_value()
        if self.config.provider in {"openai", "livai"}:
            return OpenAIChatModel(
                self.config.model_name,
                provider=OpenAIProvider(
                    api_key=api_key,
                    base_url=self.config.base_url,
                    http_client=http_client,
                ),
            )
        return AnthropicModel(
            self.config.model_name,
            provider=AnthropicProvider(api_key=api_key, http_client=http_client),
        )

    def _build_model_settings(self) -> ModelSettings:
        return {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

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
