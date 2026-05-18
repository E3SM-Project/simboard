# Plan: Phase 2 LLM Integration for Issue #52 Using Pydantic AI

## Summary

Add backend-managed LLM summary generation to the existing simulation summary flow while preserving the current endpoint and detail-page summary panel. Use **Pydantic AI** as the adapter/orchestration layer, support **OpenAI**, **Anthropic**, and **LivAI** behind a **backend config switch**, and keep the current deterministic summary generator as the mandatory fallback whenever LLM generation is disabled, misconfigured, invalid, or fails.

## Key Changes

### 1. Refactor the assistant backend into explicit phases

Restructure the existing assistant feature into five responsibilities:

- **Citation path registry**: define a `VALID_CITATION_PATHS: frozenset[str]` (or a structured registry keyed by `source_type`) in the assistant feature that enumerates every citation path the snapshot builder can produce. This is the single source of truth for citation validation. Update the registry whenever new metadata fields are added to the snapshot.
- **Metadata snapshot builder**: derive one canonical, structured simulation context object as a **dedicated Pydantic model** (`SimulationSnapshot`) from `Simulation` ORM data. The snapshot model must use explicit field assignment — never serialize the ORM model directly — and must **exclude PII** (`created_by`, `last_updated_by`, user emails/roles). Only fields present in the citation path registry are included. If the snapshot exceeds a configurable size budget (character or token limit), truncate or sample artifacts/links and add a caveat noting the truncation.
- **Deterministic renderer**: keep the current metadata-only summary builder as the non-LLM fallback path.
- **Pydantic AI summary generator**: define a typed output model matching the public summary response and use Pydantic AI to request structured output from the configured provider.
- **Summary orchestrator**: decide whether to use LLM generation, validate the result against the citation path registry, and fall back to deterministic output when needed.

This keeps metadata extraction centralized, prevents divergence between deterministic and LLM outputs, and ensures no PII is transmitted to external providers.

**Likely file mapping** (new files under `backend/app/features/assistant/`):

| Responsibility                | File                    |
| ----------------------------- | ----------------------- |
| Citation path registry        | `registry.py`           |
| Metadata snapshot builder     | `snapshot.py`           |
| Deterministic renderer        | `service.py` (existing) |
| Pydantic AI summary generator | `llm_generator.py`      |
| Summary orchestrator          | `orchestrator.py`       |

### 2. Use Pydantic AI with a config-switched provider model

Add assistant LLM settings in `backend/app/core/config.py` and corresponding example env templates:

- `assistant_llm_enabled`
- `assistant_llm_provider` with values `openai`, `anthropic`, or `livai`
- `assistant_openai_api_key` (declare as `pydantic.SecretStr` to prevent leaking in repr/logs)
- `assistant_openai_model`
- `assistant_anthropic_api_key` (declare as `pydantic.SecretStr`)
- `assistant_anthropic_model`
- `assistant_livai_api_key` (canonical env name `ASSISTANT_LIVAI_API_KEY`; legacy alias `LIVAI_API_KEY` accepted)
- `assistant_livai_model`
- `assistant_livai_base_url` (canonical env name `ASSISTANT_LIVAI_BASE_URL`; legacy alias `LIVAI_BASE_URL` accepted)
- `assistant_llm_timeout_seconds`
- `assistant_snapshot_max_chars` (optional, default sensible limit e.g. 12000)

Use **one active provider at runtime** selected by config. Do not add per-request provider selection, provider fan-out, or UI provider controls.

Use Pydantic AI to:

- select the model implementation from config
- enforce typed structured output
- keep provider-specific code minimal and localized

If Pydantic AI still requires provider SDK dependencies for the selected models, add only the necessary packages to `backend/pyproject.toml`.

### 3. Migrate endpoint to async and extend the response minimally

Migrate the endpoint handler from `def summarize_simulation` to `async def summarize_simulation` and use Pydantic AI's async interface for provider calls. The deterministic fallback path has no blocking I/O, so the migration is safe. This prevents long-running LLM network calls from exhausting the sync threadpool under concurrent requests.

**Async DB session strategy**: The current endpoint injects a sync `Session` via `get_database_session` and calls `db.query()`. Inside an `async def` handler these calls would block the event loop. Migrate the endpoint's DB queries to use the existing async session infrastructure (`get_async_session` from `backend/app/core/database_async.py`, async SQLAlchemy). The repo already has `AsyncSessionLocal`, `get_async_session`, and corresponding async test fixtures (`async_db`, `async_client`), so no new infrastructure is needed. The `current_active_user` dependency already uses `AsyncSession` internally.

Preserve the existing endpoint path:

- `POST /simulations/{sim_id}/summary`

Keep the existing response fields and add generation metadata with **deterministic nullability rules**:

- `generation_mode`: `"llm"` or `"deterministic"` — always present, never null.
- `generation_provider`: `"openai"`, `"anthropic"`, `"livai"`, or `null` — **always `null` when `generation_mode` is `"deterministic"`** (including fallback). Provider identity on fallback is captured only in server logs, not in the response.
- `generation_model`: configured model name or `null` — same nullability rule as `generation_provider`.

Existing fields remain:

- `answer`
- `citations`
- `assumptions`
- `caveats`
- `limitations`
- `suggested_followups`
- `trace_id`

Frontend types should add the three new fields as **optional** (`generationMode?: ...`) so the frontend is backward-compatible during rolling deploys. Rendering logic should default to `"deterministic"` when the fields are absent. The current simulation details UX should stay as a read-only summary panel rather than changing interaction patterns.

### 4. Ground and validate LLM output before returning it

The LLM must not return freeform prose directly to the API response. Require it to produce schema-valid structured output through Pydantic AI, then validate:

- citations reference only metadata paths present in the canonical snapshot
- citation source types remain within the existing allowed enum values
- required sections are present and non-empty where expected
- diagnostics are not interpreted beyond metadata unless the source data already contains that interpretation

**Prompt template location**: The system prompt is a module-level constant (`SUMMARY_SYSTEM_PROMPT`) in the LLM generator module (`llm_generator.py`). This keeps it version-controlled, grep-able, and testable without adding file-loading complexity.

Prompting should instruct the model to:

- summarize only the provided metadata snapshot
- avoid scientific conclusions not present in source metadata
- use caveats when metadata is missing
- keep citations metadata-grounded only
- avoid retrieval, external knowledge, and hidden assumptions

If validation fails, parsing fails, provider calls error, or configuration is incomplete:

- log the failure reason (correlated with the existing `trace_id` on the same structured log line)
- generate the deterministic summary instead
- return `generation_mode="deterministic"` with `generation_provider=null` and `generation_model=null`
- include a standardized caveat string indicating fallback was used (e.g. "This summary was generated using the deterministic fallback because the LLM path was unavailable.") to keep frontend rendering consistent

### 5. Preserve the current frontend interaction model

Reuse the existing simulation details summary panel and button. Do not add chat UI, freeform prompts, compare integration, or multi-turn state.

Frontend changes should be limited to:

- accepting the new generation metadata fields
- showing whether the summary came from the LLM path or deterministic fallback
- optionally surfacing provider/model in a small secondary disclosure
- preserving existing auth, loading, error, and retry behavior

The panel remains contextual to a single simulation and read-only.

### 6. Extend logging and observability

Keep the current per-request assistant logging and append new fields to the **same structured log line** that already carries `trace_id`:

- `generation_mode`
- `generation_provider`
- `generation_model`
- `fallback_reason` when deterministic fallback is used
- `llm_latency_ms` separate from total `latency_ms`

All new log fields share the existing `trace_id` key for correlation.

If Pydantic AI or the underlying provider exposes token/usage metadata cheaply, log it opportunistically, but do not add it to the public API in this phase.

## Test Plan

### Backend

Add or update assistant tests to cover:

- LLM disabled returns deterministic output with `generation_mode="deterministic"`, `generation_provider=null`, `generation_model=null`
- config switch selects OpenAI path; mock returns valid structured output
- config switch selects Anthropic path; mock returns valid structured output
- config switch selects LivAI path; mock returns valid structured output
- provider misconfiguration falls back deterministically with standardized caveat
- provider exception falls back deterministically with standardized caveat
- schema-invalid LLM output falls back deterministically
- citations referencing paths not in `VALID_CITATION_PATHS` are rejected and fall back deterministically
- successful LLM output returns structured response with `generation_mode="llm"`
- auth and `404` behavior remain unchanged
- `async def` endpoint returns correctly for both LLM and deterministic paths
- snapshot builder excludes PII fields (`created_by`, `last_updated_by`, user emails/roles)
- snapshot truncation fires when artifact/link count exceeds `assistant_snapshot_max_chars`; caveat is added
- API key config fields are `SecretStr` and do not appear in `repr()` or log output
- response contract is stable: all three generation metadata fields are always present with correct nullability
- fallback log line includes `trace_id`, `fallback_reason`, `generation_mode`

Mock provider/model calls in tests. Do not depend on live network access or real API keys.

**Note on test client**: The existing sync `TestClient` fixture handles `async def` endpoints correctly (Starlette runs an internal event loop). However, once the endpoint migrates from `get_database_session` (sync) to `get_async_session` (async), the existing `db` fixture override no longer targets the right dependency. Existing assistant API tests must migrate to the `async_client` / `async_db` fixtures from `conftest.py` and override `get_async_session` instead. The repo already has these async test fixtures, so no new infrastructure is needed.

### Frontend

Update existing frontend typing/render coverage to verify:

- summary response type accepts generation metadata as optional fields
- summary panel renders LLM vs deterministic badge correctly
- fallback disclosure (standardized caveat) does not break existing summary rendering
- response with missing generation metadata fields (rolling deploy compat) defaults gracefully
- existing login-required behavior remains unchanged

### Commands

- `make backend-test`
- `make frontend-lint`
- `pnpm --dir frontend run type-check`
- `make pre-commit-run`

## Assumptions

- Phase 2 uses **Pydantic AI** as the thin LLM orchestration layer.
- Support for OpenAI, Anthropic, and LivAI means **one provider selected by backend config**, not per-request choice and not automatic provider failover.
- Deterministic fallback remains mandatory and automatic.
- No retrieval, RAG, curated document indexing, compare workflows, persistence, chat UI, or frontend interaction redesign is included in this phase.
- Public API shape should remain stable aside from the minimal generation metadata additions above.
