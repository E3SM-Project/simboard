from typing import cast

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.features.assistant import orchestrator
from app.features.assistant.schemas import SimulationSummaryContent, SummaryCitationOut
from app.features.assistant.service import LLM_FALLBACK_CAVEAT
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    SnapshotArtifact,
    SnapshotCaseFields,
    SnapshotLink,
    SnapshotSimulationFields,
)
from app.features.simulation.models import Simulation

DEFAULT_LIVAI_API_KEY = SecretStr("livai-key")


def _make_snapshot() -> SimulationSnapshot:
    return SimulationSnapshot(
        simulation=SnapshotSimulationFields(
            id="simulation-1",
            execution_id="assistant-livai-exec",
            description="LivAI-backed simulation summary test.",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            simulation_type="experimental",
            status="completed",
            campaign="historical",
            experiment_type="historical",
            initialization_type="startup",
            simulation_start_date="2023-01-01T00:00:00Z",
            simulation_end_date="2023-12-31T00:00:00Z",
            git_tag="v1.0.0",
        ),
        case=SnapshotCaseFields(
            name="assistant_livai_case",
            reference_simulation_id="simulation-1",
        ),
        snapshot_caveats=[],
    )


def _make_llm_content(**overrides) -> SimulationSummaryContent:
    payload = {
        "answer": "Simulation assistant-livai-exec belongs to case assistant_livai_case.",
        "citations": [
            SummaryCitationOut(
                source_type="simulation_field",
                path="simulation.execution_id",
                label="Execution ID",
            ),
            SummaryCitationOut(
                source_type="case_field",
                path="case.name",
                label="Case Name",
            ),
        ],
        "assumptions": [],
        "caveats": [],
        "limitations": ["Custom LLM caveat."],
        "suggested_followups": ["Review recorded artifacts."],
    }
    payload.update(overrides)
    return SimulationSummaryContent(**payload)


def _set_livai_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    api_key: SecretStr | None = DEFAULT_LIVAI_API_KEY,
    model: str | None = "livai-model",
    base_url: str = "https://api.livai.llnl.gov/v1",
) -> None:
    monkeypatch.setattr(settings, "assistant_llm_enabled", enabled)
    monkeypatch.setattr(settings, "assistant_llm_provider", "livai")
    monkeypatch.setattr(settings, "assistant_livai_api_key", api_key)
    monkeypatch.setattr(settings, "assistant_livai_model", model)
    monkeypatch.setattr(settings, "assistant_livai_base_url", base_url)
    monkeypatch.setattr(settings, "assistant_llm_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "assistant_llm_temperature", 0.2)
    monkeypatch.setattr(settings, "assistant_llm_max_tokens", 2048)


class TestResolveLLMConfig:
    def test_resolve_llm_config_for_openai_returns_expected_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assistant_llm_provider", "openai")
        monkeypatch.setattr(
            settings, "assistant_openai_api_key", SecretStr("openai-key")
        )
        monkeypatch.setattr(settings, "assistant_openai_model", "gpt-test")
        monkeypatch.setattr(settings, "assistant_llm_timeout_seconds", 20.0)
        monkeypatch.setattr(settings, "assistant_llm_temperature", 0.2)
        monkeypatch.setattr(settings, "assistant_llm_max_tokens", 2048)

        config = orchestrator._resolve_llm_config()

        assert config.provider == "openai"
        assert config.model_name == "gpt-test"
        assert config.api_key.get_secret_value() == "openai-key"
        assert config.temperature == 0.2
        assert config.max_tokens == 2048

    def test_resolve_llm_config_for_livai_uses_wrapper_key_and_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_livai_settings(monkeypatch)

        config = orchestrator._resolve_llm_config()

        assert config.provider == "livai"
        assert config.model_name == "livai-model"
        assert config.api_key.get_secret_value() == "livai-key"
        assert config.base_url == "https://api.livai.llnl.gov/v1"

    def test_resolve_llm_config_for_anthropic_returns_expected_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assistant_llm_provider", "anthropic")
        monkeypatch.setattr(
            settings, "assistant_anthropic_api_key", SecretStr("anthropic-key")
        )
        monkeypatch.setattr(settings, "assistant_anthropic_model", "claude-test")
        monkeypatch.setattr(settings, "assistant_llm_timeout_seconds", 15.0)
        monkeypatch.setattr(settings, "assistant_llm_temperature", 0.2)
        monkeypatch.setattr(settings, "assistant_llm_max_tokens", 2048)

        config = orchestrator._resolve_llm_config()

        assert config.provider == "anthropic"
        assert config.model_name == "claude-test"
        assert config.api_key.get_secret_value() == "anthropic-key"
        assert config.temperature == 0.2
        assert config.max_tokens == 2048

    def test_resolve_llm_config_rejects_openai_misconfiguration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assistant_llm_provider", "openai")
        monkeypatch.setattr(settings, "assistant_openai_api_key", None)
        monkeypatch.setattr(settings, "assistant_openai_model", "gpt-test")

        with pytest.raises(ValueError, match="openai_misconfigured"):
            orchestrator._resolve_llm_config()

    def test_resolve_llm_config_rejects_anthropic_misconfiguration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assistant_llm_provider", "anthropic")
        monkeypatch.setattr(settings, "assistant_anthropic_api_key", None)
        monkeypatch.setattr(settings, "assistant_anthropic_model", "claude-test")

        with pytest.raises(ValueError, match="anthropic_misconfigured"):
            orchestrator._resolve_llm_config()

    def test_resolve_llm_config_rejects_unsupported_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assistant_llm_provider", "unsupported")

        with pytest.raises(ValueError, match="unsupported_provider"):
            orchestrator._resolve_llm_config()

    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("openai", "gpt-test"),
            ("anthropic", "claude-test"),
            ("livai", "livai-model"),
        ],
    )
    def test_configured_model_name_uses_provider_setting(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: str,
        expected: str,
    ) -> None:
        from app.features.assistant.schemas import SummaryGenerationProvider

        monkeypatch.setattr(settings, "assistant_openai_model", "gpt-test")
        monkeypatch.setattr(settings, "assistant_anthropic_model", "claude-test")
        monkeypatch.setattr(settings, "assistant_livai_model", "livai-model")

        assert (
            orchestrator._configured_model_name(
                cast(SummaryGenerationProvider, provider)
            )
            == expected
        )


class TestValidationHelpers:
    def test_standardize_citations_rejects_invalid_path(self) -> None:
        with pytest.raises(ValueError, match="invalid_citation_path:invalid.path"):
            orchestrator._standardize_citations(
                [
                    SummaryCitationOut(
                        source_type="simulation_field",
                        path="invalid.path",
                        label="Invalid",
                    )
                ],
                _make_snapshot(),
            )

    def test_standardize_citations_rejects_missing_snapshot_path(self) -> None:
        with pytest.raises(ValueError, match="missing_citation_path:machine.name"):
            orchestrator._standardize_citations(
                [
                    SummaryCitationOut(
                        source_type="machine_field",
                        path="machine.name",
                        label="Machine",
                    )
                ],
                _make_snapshot(),
            )

    @pytest.mark.parametrize(
        ("overrides", "expected_error"),
        [
            ({"answer": "   "}, "empty_answer"),
            ({"citations": []}, "missing_citations"),
            ({"limitations": []}, "missing_limitations"),
            ({"suggested_followups": []}, "missing_followups"),
        ],
    )
    def test_validate_llm_content_requires_all_required_fields(
        self,
        overrides: dict[str, object],
        expected_error: str,
    ) -> None:
        with pytest.raises(ValueError, match=expected_error):
            orchestrator._validate_llm_content(
                _make_llm_content(**overrides),
                _make_snapshot(),
            )

    def test_snapshot_has_citation_path_supports_related_record_selectors(self) -> None:
        snapshot = _make_snapshot().model_copy(
            update={
                "artifacts": [SnapshotArtifact(kind="output", uri="s3://bucket/out")],
                "links": [
                    SnapshotLink(kind="diagnostic", url="https://diag.example.com")
                ],
            }
        )

        assert orchestrator.snapshot_has_citation_path(
            snapshot, "artifacts[kind=output]"
        )
        assert orchestrator.snapshot_has_citation_path(
            snapshot, "links[kind=diagnostic]"
        )
        assert not orchestrator.snapshot_has_citation_path(snapshot, "links[kind=docs]")
        assert not orchestrator.snapshot_has_citation_path(snapshot, "invalid.path")


class TestGenerateSimulationSummary:
    @pytest.mark.asyncio
    async def test_generate_simulation_summary_returns_deterministic_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        monkeypatch.setattr(settings, "assistant_llm_enabled", False)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "llm_disabled"
        assert result.summary.generation_mode == "deterministic"
        assert result.attempted_provider is None
        assert result.attempted_model is None

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_returns_livai_provider_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            return SimulationSummaryContent(
                answer="Simulation assistant-livai-exec belongs to case assistant_livai_case.",
                citations=[
                    SummaryCitationOut(
                        source_type="simulation_field",
                        path="simulation.execution_id",
                        label="Execution ID",
                    ),
                    SummaryCitationOut(
                        source_type="case_field",
                        path="case.name",
                        label="Case Name",
                    ),
                ],
                assumptions=[],
                caveats=[],
                limitations=["Custom LLM caveat."],
                suggested_followups=["Review recorded artifacts."],
            )

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "llm"
        assert result.summary.generation_provider == "livai"
        assert result.summary.generation_model == "livai-model"
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_falls_back_for_livai_misconfiguration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch, api_key=None)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "livai_misconfigured"
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.generation_provider is None
        assert result.summary.generation_model is None
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"
        assert LLM_FALLBACK_CAVEAT in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_falls_back_on_invalid_llm_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            return _make_llm_content(limitations=[])

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "missing_limitations"
        assert result.summary.generation_mode == "deterministic"
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"
        assert LLM_FALLBACK_CAVEAT in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_falls_back_on_unexpected_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "RuntimeError"
        assert result.summary.generation_mode == "deterministic"
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"
