# AI-196 Local LLM Plan

Issue: [#196](https://github.com/E3SM-Project/simboard/issues/196)

## Task

Add locally hosted LLM provider support, starting with Ollama, by extending the existing `dev-ai` assistant summary backend.

## Scope

### In scope

- Extend assistant provider config and runtime selection in backend.
- Add Ollama/local endpoint and model support for existing summary generation flow.
- Update env templates and developer/deployment docs.
- Add backend tests for config, provider resolution, client construction, and fallback behavior.

### Out of scope

- New frontend model or provider controls.
- Shipping Ollama container manifests or Docker Compose setup.
- Retrieval, tool use, or broader agent features beyond the current summary endpoint.

## Approach

1. Extend provider enums and config types in [backend/app/features/assistant/schemas.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/schemas.py) and [backend/app/core/config.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/core/config.py) to include `ollama`.
2. Add Ollama settings in config and env docs:
   - `ASSISTANT_OLLAMA_BASE_URL`
   - `ASSISTANT_OLLAMA_MODEL`
   - optional auth/header setting only if a real deployment needs it
3. Refactor provider resolution in [backend/app/features/assistant/orchestrator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/orchestrator.py) so Ollama becomes one more supported provider without changing deterministic fallback behavior.
4. Update [backend/app/features/assistant/llm_generator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/llm_generator.py) to build the Ollama/local client.
5. Prefer the existing OpenAI-compatible path if Ollama works with the current `pydantic_ai` structured output contract; otherwise add the smallest provider-specific branch needed for Ollama.
6. Keep the assistant API and response schema unchanged unless local-provider constraints force a change.
7. Preserve current logging and fallback semantics:
   - attempted provider/model logged
   - deterministic fallback on misconfig, timeout, unreachable endpoint, or invalid structured output
8. Update docs and examples in:
   - [.envs/example/backend.env.example](/Users/vo13/Repositories/tomvothecoder/simboard/.envs/example/backend.env.example)
   - [.envs/example/backend.production.env.example](/Users/vo13/Repositories/tomvothecoder/simboard/.envs/example/backend.production.env.example)
   - [backend/README.md](/Users/vo13/Repositories/tomvothecoder/simboard/backend/README.md)
   - [docs/developer/README.md](/Users/vo13/Repositories/tomvothecoder/simboard/docs/developer/README.md)
   - [docs/deploy/spin.md](/Users/vo13/Repositories/tomvothecoder/simboard/docs/deploy/spin.md) if Spin secret/env guidance should mention assistant vars

## Tests

### Tests to add or update

- [backend/tests/core/test_config.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/core/test_config.py)
  - Ollama env vars load and normalize correctly.
- [backend/tests/features/assistant/test_orchestrator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_orchestrator.py)
  - Ollama config resolves.
  - Ollama misconfig falls back with a stable reason.
  - Ollama success reports `generation_provider == "ollama"`.
- [backend/tests/features/assistant/test_llm_generator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_llm_generator.py)
  - Client/model builder uses the Ollama base URL correctly.
  - Model settings remain compatible with local provider behavior.
- Optional: [backend/tests/features/assistant/test_api.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_api.py)
  - Summary route still returns deterministic fallback when the Ollama path fails.

### Commands to run

- `make backend-test`
- Optional focused loop:
  - `uv run pytest backend/tests/core/test_config.py backend/tests/features/assistant/test_llm_generator.py backend/tests/features/assistant/test_orchestrator.py`

## Risk

- Risk score: `4`

### Main failure modes

- Ollama is not fully compatible with the current structured-output/client path.
- Local models produce weaker schema adherence and trigger fallback churn.
- Provider config grows too provider-specific if the abstraction is not kept tight.
- Docs drift between local and Spin deployment setup.

## Open Questions

None.
