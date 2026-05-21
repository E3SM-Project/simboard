from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai.output import PromptedOutput

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
            temperature=0.2,
            max_tokens=2048,
            base_url="https://example.livai.test/v1",
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert str(model.client.base_url) == "https://example.livai.test/v1/"

    @pytest.mark.asyncio
    async def test_build_model_normalizes_ollama_root_url_to_v1(self) -> None:
        config = AssistantLLMConfig(
            provider="ollama",
            model_name="gemma4:26b",
            api_key=None,
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="http://localhost:11434",
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert str(model.client.base_url) == "http://localhost:11434/v1/"

    @pytest.mark.asyncio
    async def test_build_model_preserves_explicit_ollama_v1_base_url(self) -> None:
        config = AssistantLLMConfig(
            provider="ollama",
            model_name="gemma4:e4b",
            api_key=SecretStr("ollama-key"),
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="http://localhost:11434/v1",
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert str(model.client.base_url) == "http://localhost:11434/v1/"
        assert model.client.max_retries == 0

    @pytest.mark.asyncio
    async def test_build_model_keeps_default_retries_for_livai(self) -> None:
        config = AssistantLLMConfig(
            provider="livai",
            model_name="livai-model",
            api_key=SecretStr("livai-key"),
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="https://example.livai.test/v1",
        )

        async with AsyncClient() as http_client:
            model = SummaryLLMGenerator(config)._build_model(http_client=http_client)

        assert model.client.max_retries == 2

    def test_build_model_settings_omits_temperature_for_livai_gpt5(self) -> None:
        config = AssistantLLMConfig(
            provider="livai",
            model_name="gpt-5.4-mini",
            api_key=SecretStr("livai-key"),
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="https://example.livai.test/v1",
        )

        assert SummaryLLMGenerator(config)._build_model_settings() == {
            "max_tokens": 2048,
        }

    def test_build_model_settings_keeps_tuning_for_non_gpt5_livai(self) -> None:
        config = AssistantLLMConfig(
            provider="livai",
            model_name="gpt-4.1-mini",
            api_key=SecretStr("livai-key"),
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="https://example.livai.test/v1",
        )

        assert SummaryLLMGenerator(config)._build_model_settings() == {
            "temperature": 0.2,
            "max_tokens": 2048,
        }

    def test_build_model_settings_includes_tuning_for_ollama(self) -> None:
        config = AssistantLLMConfig(
            provider="ollama",
            model_name="gemma4:26b",
            api_key=None,
            timeout_seconds=30.0,
            temperature=0.2,
            max_tokens=2048,
            base_url="http://localhost:11434",
        )

        assert SummaryLLMGenerator(config)._build_model_settings() == {
            "temperature": 0.2,
            "max_tokens": 2048,
        }

    def test_build_user_prompt_includes_snapshot_and_allowed_citations(self) -> None:
        prompt = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="livai",
                model_name="livai-model",
                api_key=SecretStr("livai-key"),
                timeout_seconds=30.0,
                temperature=0.2,
                max_tokens=2048,
                base_url="https://example.livai.test/v1",
            )
        )._build_user_prompt(_make_snapshot())

        assert "assistant-llm-exec" in prompt
        assert "simulation.execution_id (simulation_field)" in prompt
        assert "case.name (case_field)" in prompt

    def test_summary_system_prompt_enforces_short_natural_answer_shape(self) -> None:
        assert (
            "Keep `answer` to 2-4 short sentences"
            in llm_generator.SUMMARY_SYSTEM_PROMPT
        )
        assert (
            "Do not enumerate every available field."
            in llm_generator.SUMMARY_SYSTEM_PROMPT
        )
        assert "Do not repeat raw citation paths" in llm_generator.SUMMARY_SYSTEM_PROMPT
        assert (
            "Every `citations.path` value must exactly match one allowed path string."
            in (llm_generator.SUMMARY_SYSTEM_PROMPT)
        )
        assert (
            "use `simulation.status`, `case.name`, and `machine.name`, not `status` or `name`."
            in llm_generator.SUMMARY_SYSTEM_PROMPT
        )
        assert "`suggested_followups` must contain at least one concrete item." in (
            llm_generator.SUMMARY_SYSTEM_PROMPT
        )

    def test_build_output_type_uses_prompted_output_for_ollama(self) -> None:
        output_type = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="ollama",
                model_name="gemma4:e4b",
                api_key=None,
                timeout_seconds=30.0,
                temperature=0.2,
                max_tokens=2048,
                base_url="http://localhost:11434",
            )
        )._build_output_type()

        assert isinstance(output_type, PromptedOutput)
        assert output_type.outputs is SimulationSummaryContent

    def test_build_output_type_keeps_native_type_for_livai(self) -> None:
        output_type = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="livai",
                model_name="livai-model",
                api_key=SecretStr("livai-key"),
                timeout_seconds=30.0,
                temperature=0.2,
                max_tokens=2048,
                base_url="https://example.livai.test/v1",
            )
        )._build_output_type()

        assert output_type is SimulationSummaryContent

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
            def __init__(
                self, model, output_type, system_prompt, model_settings=None
            ) -> None:
                captured["model"] = model
                captured["output_type"] = output_type
                captured["system_prompt"] = system_prompt
                captured["model_settings"] = model_settings

            async def run(self, prompt: str):
                captured["prompt"] = prompt
                return SimpleNamespace(output=expected)

        monkeypatch.setattr(llm_generator, "Agent", FakeAgent)

        generator = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="livai",
                model_name="livai-model",
                api_key=SecretStr("livai-key"),
                timeout_seconds=30.0,
                temperature=0.2,
                max_tokens=2048,
                base_url="https://example.livai.test/v1",
            )
        )

        result = await generator.generate(_make_snapshot())

        assert result == expected
        assert captured["output_type"] is SimulationSummaryContent
        assert captured["system_prompt"] == llm_generator.SUMMARY_SYSTEM_PROMPT
        assert captured["model_settings"] == {
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        assert "Allowed citation paths:" in str(captured["prompt"])

    @pytest.mark.asyncio
    async def test_generate_uses_prompted_output_for_ollama(
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
            def __init__(
                self, model, output_type, system_prompt, model_settings=None
            ) -> None:
                captured["model"] = model
                captured["output_type"] = output_type
                captured["system_prompt"] = system_prompt
                captured["model_settings"] = model_settings

            async def run(self, prompt: str):
                captured["prompt"] = prompt
                return SimpleNamespace(output=expected)

        monkeypatch.setattr(llm_generator, "Agent", FakeAgent)

        generator = SummaryLLMGenerator(
            AssistantLLMConfig(
                provider="ollama",
                model_name="gemma4:e4b",
                api_key=None,
                timeout_seconds=30.0,
                temperature=0.2,
                max_tokens=2048,
                base_url="http://localhost:11434",
            )
        )

        result = await generator.generate(_make_snapshot())

        assert result == expected
        assert isinstance(captured["output_type"], PromptedOutput)
