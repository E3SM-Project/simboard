from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.features.assistant import llm_generator
from app.features.assistant.llm_generator import AssistantLLMConfig, SummaryLLMGenerator
from app.features.assistant.schemas import SimulationSummaryContent, SummaryCitationOut
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    SnapshotCaseFields,
    SnapshotSimulationFields,
)


def _make_snapshot() -> SimulationSnapshot:
    return SimulationSnapshot(
        simulation=SnapshotSimulationFields(
            id="simulation-1",
            execution_id="assistant-llm-exec",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            simulation_type="experimental",
            status="completed",
            initialization_type="startup",
        ),
        case=SnapshotCaseFields(name="assistant_case"),
    )


class TestSummaryLLMGenerator:
    @pytest.mark.asyncio
    async def test_build_model_uses_livai_base_url_for_openai_compatible_provider(
        self,
    ):
        config = AssistantLLMConfig(
            provider="livai",
            model_name="livai-model",
            api_key=SecretStr("livai-key"),
            timeout_seconds=30.0,
            base_url="https://example.livai.test/v1",
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert str(model.client.base_url) == "https://example.livai.test/v1/"

    @pytest.mark.asyncio
    async def test_build_model_uses_anthropic_provider(self) -> None:
        config = AssistantLLMConfig(
            provider="anthropic",
            model_name="claude-test",
            api_key=SecretStr("anthropic-key"),
            timeout_seconds=30.0,
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert model.__class__.__name__ == "AnthropicModel"

    def test_build_user_prompt_includes_snapshot_and_allowed_citations(self) -> None:
        prompt = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="openai",
                model_name="gpt-test",
                api_key=SecretStr("openai-key"),
                timeout_seconds=30.0,
            )
        )._build_user_prompt(_make_snapshot())

        assert "assistant-llm-exec" in prompt
        assert "simulation.execution_id (simulation_field)" in prompt
        assert "case.name (case_field)" in prompt

    @pytest.mark.asyncio
    async def test_generate_returns_agent_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected = SimulationSummaryContent(
            answer="Generated summary.",
            citations=[
                SummaryCitationOut(
                    source_type="simulation_field",
                    path="simulation.execution_id",
                    label="Execution ID",
                )
            ],
            assumptions=[],
            caveats=[],
            limitations=["limit"],
            suggested_followups=["follow up"],
        )
        captured: dict[str, object] = {}

        class FakeAgent:
            def __init__(self, model, output_type, system_prompt) -> None:
                captured["model"] = model
                captured["output_type"] = output_type
                captured["system_prompt"] = system_prompt

            async def run(self, prompt: str):
                captured["prompt"] = prompt
                return SimpleNamespace(output=expected)

        monkeypatch.setattr(llm_generator, "Agent", FakeAgent)

        generator = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="openai",
                model_name="gpt-test",
                api_key=SecretStr("openai-key"),
                timeout_seconds=30.0,
            )
        )

        result = await generator.generate(_make_snapshot())

        assert result == expected
        assert captured["output_type"] is SimulationSummaryContent
        assert captured["system_prompt"] == llm_generator.SUMMARY_SYSTEM_PROMPT
        assert "Allowed citation paths:" in str(captured["prompt"])
