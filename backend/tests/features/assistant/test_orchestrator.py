from typing import cast

import pytest
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from app.core.config import settings
from app.features.assistant import orchestrator
from app.features.assistant.schemas import (
    SimulationSummaryContent,
    SummaryCitationOut,
    SummaryGenerationProvider,
)
from app.features.assistant.service import LLM_FALLBACK_CAVEAT
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    SnapshotArtifact,
    SnapshotBudgetExceededError,
    SnapshotCaseFields,
    SnapshotLink,
    SnapshotMachineFields,
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
        case=SnapshotCaseFields(name="assistant_livai_case"),
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


def _set_ollama_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    api_key: SecretStr | None = None,
    model: str | None = "gemma4:26b",
    base_url: str = "http://localhost:11434",
) -> None:
    monkeypatch.setattr(settings, "assistant_llm_enabled", enabled)
    monkeypatch.setattr(settings, "assistant_llm_provider", "ollama")
    monkeypatch.setattr(settings, "assistant_ollama_api_key", api_key)
    monkeypatch.setattr(settings, "assistant_ollama_model", model)
    monkeypatch.setattr(settings, "assistant_ollama_base_url", base_url)
    monkeypatch.setattr(settings, "assistant_llm_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "assistant_llm_temperature", 0.2)
    monkeypatch.setattr(settings, "assistant_llm_max_tokens", 2048)


class TestResolveLLMConfig:
    def test_resolve_llm_config_for_livai_uses_wrapper_key_and_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_livai_settings(monkeypatch)

        config = orchestrator._resolve_llm_config()

        assert config.provider == "livai"
        assert config.model_name == "livai-model"
        assert config.api_key is not None
        assert config.api_key.get_secret_value() == "livai-key"
        assert config.base_url == "https://api.livai.llnl.gov/v1"

    @pytest.mark.parametrize("model_name", ["gemma4:e4b", "gemma4:26b"])
    def test_resolve_llm_config_for_ollama_uses_configured_model_and_base_url(
        self, monkeypatch: pytest.MonkeyPatch, model_name: str
    ) -> None:
        _set_ollama_settings(monkeypatch, model=model_name)

        config = orchestrator._resolve_llm_config()

        assert config.provider == "ollama"
        assert config.model_name == model_name
        assert config.api_key is None
        assert config.base_url == "http://localhost:11434"

    @pytest.mark.parametrize(
        ("model", "base_url"),
        [
            (None, "http://localhost:11434"),
            ("gemma4:26b", ""),
        ],
    )
    def test_resolve_llm_config_rejects_ollama_misconfiguration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        model: str | None,
        base_url: str,
    ) -> None:
        _set_ollama_settings(monkeypatch, model=model, base_url=base_url)

        with pytest.raises(ValueError, match="ollama_misconfigured"):
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
            ("livai", "livai-model"),
            ("ollama", "gemma4:26b"),
        ],
    )
    def test_configured_model_name_uses_provider_setting(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: SummaryGenerationProvider,
        expected: str,
    ) -> None:
        monkeypatch.setattr(settings, "assistant_livai_model", "livai-model")
        monkeypatch.setattr(settings, "assistant_ollama_model", "gemma4:26b")

        assert orchestrator._configured_model_name(provider) == expected

    def test_is_summary_llm_available_returns_true_for_valid_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_ollama_settings(monkeypatch)

        assert orchestrator.is_summary_llm_available() is True

    def test_is_summary_llm_available_returns_false_for_misconfigured_enabled_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_ollama_settings(monkeypatch, model=None)

        assert orchestrator.is_summary_llm_available() is False

    def test_is_summary_llm_available_returns_false_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_livai_settings(monkeypatch, enabled=False)

        assert orchestrator.is_summary_llm_available() is False


class TestValidationHelpers:
    def test_normalize_llm_answer_strips_inline_citation_markers(self) -> None:
        answer = (
            "This simulation completed [simulation.status]. It ran on chrysalis "
            "[machine.name] and used WCYCL20TR [simulation.compset]."
        )

        assert orchestrator._normalize_llm_answer(answer) == (
            "This simulation completed. It ran on chrysalis and used WCYCL20TR."
        )

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

    def test_standardize_citations_canonicalizes_unambiguous_suffix_path(self) -> None:
        result = orchestrator._standardize_citations(
            [
                SummaryCitationOut(
                    source_type="simulation_field",
                    path="status",
                    label="Status",
                )
            ],
            _make_snapshot(),
        )

        assert result == [
            SummaryCitationOut(
                source_type="simulation_field",
                path="simulation.status",
                label="Simulation status",
            )
        ]

    def test_canonicalize_citation_path_uses_unique_suffix_without_source_type(
        self,
    ) -> None:
        assert orchestrator._canonicalize_citation_path("status") == "simulation.status"

    def test_standardize_citations_rejects_ambiguous_suffix_path(self) -> None:
        with pytest.raises(ValueError, match="invalid_citation_path:name"):
            orchestrator._standardize_citations(
                [
                    SummaryCitationOut(
                        source_type="simulation_field",
                        path="name",
                        label="Name",
                    )
                ],
                _make_snapshot(),
            )

    def test_standardize_citations_uses_source_type_to_disambiguate_suffix_path(
        self,
    ) -> None:
        result = orchestrator._standardize_citations(
            [
                SummaryCitationOut(
                    source_type="case_field",
                    path="name",
                    label="Name",
                )
            ],
            _make_snapshot(),
        )

        assert result == [
            SummaryCitationOut(
                source_type="case_field",
                path="case.name",
                label="Case name",
            )
        ]

    def test_standardize_citations_uses_source_type_for_machine_name_suffix_path(
        self,
    ) -> None:
        snapshot = _make_snapshot().model_copy(
            update={"machine": SnapshotMachineFields(name="perlmutter")}
        )

        result = orchestrator._standardize_citations(
            [
                SummaryCitationOut(
                    source_type="machine_field",
                    path="name",
                    label="Name",
                )
            ],
            snapshot,
        )

        assert result == [
            SummaryCitationOut(
                source_type="machine_field",
                path="machine.name",
                label="Machine name",
            )
        ]

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

    def test_validate_llm_content_normalizes_inline_citation_markers(self) -> None:
        result = orchestrator._validate_llm_content(
            _make_llm_content(
                answer=(
                    "Simulation assistant-livai-exec belongs to case "
                    "assistant_livai_case [case.name]."
                )
            ),
            _make_snapshot(),
        )

        assert result.answer == (
            "Simulation assistant-livai-exec belongs to case assistant_livai_case."
        )

    def test_fill_missing_llm_followups_uses_deterministic_followups(self) -> None:
        snapshot = _make_snapshot()

        result = orchestrator._fill_missing_llm_followups(
            _make_llm_content(suggested_followups=[]),
            snapshot,
        )

        assert result.suggested_followups == (
            orchestrator.build_simulation_summary(snapshot).suggested_followups
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

        assert orchestrator._snapshot_has_citation_path(
            snapshot, "artifacts[kind=output]"
        )
        assert orchestrator._snapshot_has_citation_path(
            snapshot, "links[kind=diagnostic]"
        )
        assert not orchestrator._snapshot_has_citation_path(
            snapshot, "links[kind=docs]"
        )
        assert not orchestrator._snapshot_has_citation_path(snapshot, "invalid.path")

    def test_format_model_error_uses_exception_name_when_message_blank(self) -> None:
        assert orchestrator._format_model_error(Exception()) == "Exception"

    def test_trim_fallback_reason_adds_ellipsis_when_limit_exceeded(self) -> None:
        assert orchestrator._trim_fallback_reason("abcdef", limit=5) == "ab..."


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
        assert result.summary.fallback_used is False
        assert result.attempted_provider is None
        assert result.attempted_model is None

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_returns_deterministic_when_llm_disallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        result = await orchestrator.generate_simulation_summary(
            cast(Simulation, None),
            allow_llm=False,
        )

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is False
        assert result.attempted_provider is None
        assert result.attempted_model is None
        assert LLM_FALLBACK_CAVEAT not in result.summary.caveats

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
    async def test_generate_simulation_summary_returns_ollama_provider_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model="gemma4:26b")
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            return _make_llm_content()

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "llm"
        assert result.summary.fallback_used is False
        assert result.summary.generation_provider == "ollama"
        assert result.summary.generation_model == "gemma4:26b"
        assert result.attempted_provider == "ollama"
        assert result.attempted_model == "gemma4:26b"

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
    async def test_generate_simulation_summary_falls_back_for_ollama_misconfiguration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model=None)
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "ollama_misconfigured"
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is True
        assert result.summary.generation_provider is None
        assert result.summary.generation_model is None
        assert result.attempted_provider == "ollama"
        assert result.attempted_model is None
        assert LLM_FALLBACK_CAVEAT in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_falls_back_when_snapshot_budget_exceeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)

        def fail_snapshot_build(simulation: Simulation) -> SimulationSnapshot:
            raise SnapshotBudgetExceededError(snapshot, 10)

        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            fail_snapshot_build,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason is not None
        assert result.fallback_reason.startswith("Snapshot size ")
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is True
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"
        assert LLM_FALLBACK_CAVEAT in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_keeps_deterministic_mode_when_llm_disabled_and_snapshot_budget_exceeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch, enabled=False)

        def fail_snapshot_build(simulation: Simulation) -> SimulationSnapshot:
            raise SnapshotBudgetExceededError(snapshot, 10)

        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            fail_snapshot_build,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == "llm_disabled"
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is False
        assert result.attempted_provider is None
        assert result.attempted_model is None
        assert LLM_FALLBACK_CAVEAT not in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_returns_deterministic_when_llm_disallowed_and_snapshot_budget_exceeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_livai_settings(monkeypatch)

        def fail_snapshot_build(simulation: Simulation) -> SimulationSnapshot:
            raise SnapshotBudgetExceededError(snapshot, 10)

        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            fail_snapshot_build,
        )

        result = await orchestrator.generate_simulation_summary(
            cast(Simulation, None),
            allow_llm=False,
        )

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is False
        assert result.attempted_provider is None
        assert result.attempted_model is None
        assert LLM_FALLBACK_CAVEAT not in result.summary.caveats

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
        assert result.summary.fallback_used is True
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"
        assert LLM_FALLBACK_CAVEAT in result.summary.caveats

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_keeps_llm_mode_when_followups_missing(
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
            return _make_llm_content(suggested_followups=[])

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
        assert result.summary.suggested_followups == (
            orchestrator.build_simulation_summary(snapshot).suggested_followups
        )
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_canonicalizes_unambiguous_citation_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model="llama3.1:8b")
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            return _make_llm_content(
                citations=[
                    SummaryCitationOut(
                        source_type="simulation_field",
                        path="status",
                        label="Status",
                    )
                ]
            )

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "llm"
        assert result.summary.generation_provider == "ollama"
        assert result.summary.generation_model == "llama3.1:8b"
        assert result.summary.citations == [
            SummaryCitationOut(
                source_type="simulation_field",
                path="simulation.status",
                label="Simulation status",
            )
        ]
        assert result.attempted_provider == "ollama"
        assert result.attempted_model == "llama3.1:8b"

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_uses_source_type_to_fix_name_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model="llama3.1:8b")
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            return _make_llm_content(
                citations=[
                    SummaryCitationOut(
                        source_type="case_field",
                        path="name",
                        label="Name",
                    )
                ]
            )

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason is None
        assert result.summary.generation_mode == "llm"
        assert result.summary.generation_provider == "ollama"
        assert result.summary.generation_model == "llama3.1:8b"
        assert result.summary.citations == [
            SummaryCitationOut(
                source_type="case_field",
                path="case.name",
                label="Case name",
            )
        ]
        assert result.attempted_provider == "ollama"
        assert result.attempted_model == "llama3.1:8b"

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

        assert result.fallback_reason == "RuntimeError: boom"
        assert result.summary.generation_mode == "deterministic"
        assert result.summary.fallback_used is True
        assert result.attempted_provider == "livai"
        assert result.attempted_model == "livai-model"

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_preserves_model_api_error_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model="gemma4:e4b")
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            raise ModelAPIError("gemma4:e4b", "unsupported value for tools")

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == ("ModelAPIError: unsupported value for tools")
        assert result.summary.generation_mode == "deterministic"
        assert result.attempted_provider == "ollama"
        assert result.attempted_model == "gemma4:e4b"

    @pytest.mark.asyncio
    async def test_generate_simulation_summary_preserves_model_http_error_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()
        _set_ollama_settings(monkeypatch, model="gemma4:e4b")
        monkeypatch.setattr(
            orchestrator,
            "build_simulation_snapshot",
            lambda simulation: snapshot,
        )

        async def fake_generate(self, snapshot_arg):
            raise ModelHTTPError(
                400,
                "gemma4:e4b",
                {"error": {"message": "unknown field `tools`"}},
            )

        monkeypatch.setattr(
            orchestrator.SummaryLLMGenerator,
            "generate",
            fake_generate,
        )

        result = await orchestrator.generate_simulation_summary(cast(Simulation, None))

        assert result.fallback_reason == (
            'ModelHTTPError: status_code=400; body={"error": {"message": "unknown field `tools`"}}'
        )
        assert result.summary.generation_mode == "deterministic"
        assert result.attempted_provider == "ollama"
        assert result.attempted_model == "gemma4:e4b"
