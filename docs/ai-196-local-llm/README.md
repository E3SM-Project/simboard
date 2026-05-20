# AI-196 Local LLM Plan

Issue: [#196](https://github.com/E3SM-Project/simboard/issues/196)

## Task

Add local LLM support for SimBoard AI-assisted simulation summaries and related assistance using Ollama as local inference runtime and Gemma 4 as preferred open-weight model family.

## Scope

### In scope

- Extend existing assistant summary backend to support local Ollama-backed generation.
- Keep backend model-configurable so runtime is not hardcoded to one Gemma 4 tag.
- Prefer Gemma 4 family for local prototype guidance and quality testing.
- Preserve source-grounded summary behavior, structured output contracts, and deterministic fallback behavior.
- Keep retrieval small, curated, and prototype-oriented when used.
- Update env templates and developer docs for local Ollama setup.
- Add backend and contract tests for config, adapter behavior, validation, fallback, and API-path coverage.

### Out of scope

- New frontend model or provider controls.
- Shipping Ollama container manifests or Docker Compose assets in this repo.
- Broad RAG architecture, vector databases, or large ingestion/indexing work for this phase.
- Non-Ollama local runtimes for this prototype.

## Recommended model path

- `gemma4:e4b`
  - Use for fast local development, adapter testing, UI iteration, and prompt-contract validation.
- `gemma4:26b`
  - Use as preferred quality target for SimBoard summaries, comparisons, and source-grounded assistance.
- `gemma4:31b`
  - Treat as optional if hardware allows and `gemma4:26b` quality is insufficient.

Plan should document Gemma 4 as recommended Ollama family, but implementation must remain model-configurable so another Ollama-served model can be swapped through config without code changes.

## Configuration

Use existing SimBoard assistant env naming rather than introducing a second env namespace.

Required repo-facing settings:

```env
ASSISTANT_LLM_ENABLED=true
ASSISTANT_LLM_PROVIDER=ollama
ASSISTANT_OLLAMA_BASE_URL=http://localhost:11434
ASSISTANT_OLLAMA_MODEL=gemma4:26b
ASSISTANT_OLLAMA_API_KEY=
ASSISTANT_LLM_TIMEOUT_SECONDS=30
ASSISTANT_LLM_TEMPERATURE=0.2
ASSISTANT_LLM_MAX_TOKENS=2048
```

Local runtime example equivalent:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:26b
```

Doc guidance should explain:

- switch to `gemma4:e4b` for fast local iteration
- switch back to `gemma4:26b` for quality checks
- use `gemma4:31b` only when local hardware supports it
- Ollama remains runtime; model tag remains config

## Implementation approach

1. Extend provider enums and config types in [backend/app/features/assistant/schemas.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/schemas.py) and [backend/app/core/config.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/core/config.py) to include `ollama`.
2. Add Ollama config fields in [backend/app/core/config.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/core/config.py):
   - `ASSISTANT_OLLAMA_BASE_URL`
   - `ASSISTANT_OLLAMA_MODEL`
   - `ASSISTANT_OLLAMA_API_KEY` if endpoint protection is required by local or proxied deployment
3. Refactor provider resolution in [backend/app/features/assistant/orchestrator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/orchestrator.py) so provider selection and model selection stay config-driven.
4. Keep integration model-agnostic through adapter boundary in [backend/app/features/assistant/llm_generator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/app/features/assistant/llm_generator.py):
   - prompt construction isolated from transport details
   - model invocation isolated behind provider/model adapter
   - response validation isolated from provider client
   - persistence and API response assembly isolated from generation path
5. Prefer existing OpenAI-compatible path if Ollama works cleanly through current `pydantic_ai` structured output flow; otherwise add smallest Ollama-specific adapter branch needed without hardcoding Gemma 4 tags into invocation logic.
6. Preserve structured output contract for summaries:
   - response shape defined in Pydantic schema
   - JSON/schema validation applied before persistence or API success response
   - invalid or incomplete model output triggers deterministic fallback
7. Keep summaries source-grounded:
   - use only SimBoard metadata and small curated context supplied by backend
   - when retrieved or injected context is used, include explicit citation/source fields tied to allowed source paths
   - reject unsupported free-form claims through validation and fallback path
8. Keep API shape stable except for extending `generation_provider` to allow `ollama`, and update [frontend/src/types/simulation.ts](/Users/vo13/Repositories/tomvothecoder/simboard/frontend/src/types/simulation.ts) to match.
9. Update docs and examples in:
   - [.envs/example/backend.env.example](/Users/vo13/Repositories/tomvothecoder/simboard/.envs/example/backend.env.example)
   - [.envs/example/backend.production.env.example](/Users/vo13/Repositories/tomvothecoder/simboard/.envs/example/backend.production.env.example)
   - [backend/README.md](/Users/vo13/Repositories/tomvothecoder/simboard/backend/README.md)
   - [docs/developer/README.md](/Users/vo13/Repositories/tomvothecoder/simboard/docs/developer/README.md)
   - document one supported local Ollama bootstrap path using upstream Ollama install/container guidance plus `gemma4:e4b` and `gemma4:26b` pull/run steps
   - [docs/deploy/spin.md](/Users/vo13/Repositories/tomvothecoder/simboard/docs/deploy/spin.md) only if deployment env guidance should mention assistant vars

## Retrieval constraints for this phase

- No broad RAG rollout.
- No vector DB requirement.
- No automatic large-context corpus assembly.
- If retrieval is used, keep it small, explicit, curated, and easy to inspect in tests and logs.

## Tests

### Tests to add or update

- [backend/tests/core/test_config.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/core/test_config.py)
  - Ollama env vars load and normalize correctly.
  - `ASSISTANT_OLLAMA_MODEL` remains arbitrary string config, not hardcoded allowlist.
  - Missing base URL or model yields stable misconfiguration behavior.
- [backend/tests/features/assistant/test_orchestrator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_orchestrator.py)
  - Ollama config resolves from env-backed settings.
  - `gemma4:e4b` and `gemma4:26b` both resolve without code changes.
  - Ollama misconfig falls back with stable reason.
  - Ollama success reports `generation_provider == "ollama"` and configured model name.
- [backend/tests/features/assistant/test_llm_generator.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_llm_generator.py)
  - Client/model builder uses Ollama base URL correctly.
  - Invocation path is model-agnostic and uses configured model name.
  - Model settings remain compatible with Gemma 4 local behavior.
  - Invalid model output fails validation safely.
- [backend/tests/features/assistant/test_api.py](/Users/vo13/Repositories/tomvothecoder/simboard/backend/tests/features/assistant/test_api.py)
  - Summary route returns deterministic fallback when Ollama path fails.
  - Summary route returns `generation_provider == "ollama"` and configured model on success.
  - Response shape stays grounded and does not emit unsupported free-form fields.

### Commands to run

- `make backend-test`
- `make frontend-lint`
- Optional focused loop:
  - `uv run pytest backend/tests/core/test_config.py backend/tests/features/assistant/test_llm_generator.py backend/tests/features/assistant/test_orchestrator.py backend/tests/features/assistant/test_api.py`

## Acceptance criteria

- `ollama` is supported as assistant provider and is selectable entirely through config.
- Gemma 4 is documented as recommended Ollama model family for this prototype.
- Plan clearly distinguishes:
  - `gemma4:e4b` for fast development and prompt-contract iteration
  - `gemma4:26b` for preferred summary quality testing
  - `gemma4:31b` as optional higher-cost fallback
- Backend can call Ollama successfully using configured base URL and model name.
- Backend remains model-agnostic at adapter boundary and is not hardcoded to one Gemma 4 tag.
- Invalid JSON, schema-invalid output, or unsupported grounded fields trigger deterministic fallback rather than unsafe persistence or partial success.
- Generated summaries remain source-grounded and use explicit citation/source fields when retrieved context is included.
- `generation_provider` contract includes `ollama` and frontend type mirror stays in sync.
- `gemma4:e4b` and `gemma4:26b` can both be exercised in tests or local verification without code changes.

## Risk

- Ollama structured output behavior may differ from current hosted-provider path.
- Smaller Gemma 4 variants may pass format checks but underperform on grounded summary quality.
- `gemma4:26b` may be too heavy for some developer hardware, so docs must make `gemma4:e4b` first-run path explicit.
- If validation is too weak, local models may generate plausible but unsupported claims.
- If validation is too strict, fallback churn may hide useful outputs during prototype iteration.

## Open questions

None.
