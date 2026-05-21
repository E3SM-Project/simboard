# SimBoard Backend

The backend is a FastAPI service that ingests simulation archives, stores normalized metadata in PostgreSQL, and exposes the `/api/v1` REST API used by the frontend and service-account tooling.

## Responsibilities

- archive ingestion and validation
- case, simulation, machine, and ingestion persistence
- GitHub OAuth and API-token authentication
- PACE execution lookup
- API schemas and routing

## Important Locations

```text
backend/app/main.py                 FastAPI app and router registration
backend/app/features/ingestion/     ingestion endpoints and parser integration
backend/app/features/simulation/    cases, simulations, schemas, delta logic
backend/app/features/machine/       machine models and API
backend/app/features/user/          auth, tokens, user models
backend/app/core/                   config, DB setup, exceptions, logging
backend/migrations/                 Alembic migrations
backend/tests/                      pytest coverage
```

## Developer Commands

Run these from the repo root:

```bash
make backend-run
make backend-test
make backend-migrate m='message'
make backend-upgrade
```

## Configuration

Backend env templates live in `.envs/example/backend.env.example` and local developer values live in `.envs/local/backend.env`.

Assistant summary configuration uses the `ASSISTANT_*` namespace:

- `ASSISTANT_LLM_ENABLED`
- `ASSISTANT_LLM_PROVIDER` with `ollama` or `livai`
- `ASSISTANT_OLLAMA_API_KEY` / `ASSISTANT_OLLAMA_MODEL` / `ASSISTANT_OLLAMA_BASE_URL`
- `ASSISTANT_LIVAI_API_KEY` / `ASSISTANT_LIVAI_MODEL` / `ASSISTANT_LIVAI_BASE_URL`
- `ASSISTANT_LLM_TIMEOUT_SECONDS`
- `ASSISTANT_LLM_TEMPERATURE`
- `ASSISTANT_LLM_MAX_TOKENS`
- `ASSISTANT_SNAPSHOT_MAX_CHARS`

For local open-weight runs, prefer Ollama with one of these models:

- `llama3.1:8b` for faster local iteration on developer hardware
- `gemma4:e4b` for local quality checks when hardware and latency budget allow it
- `gemma4:26b` for preferred summary quality checks
- `gemma4:31b` only if local hardware can support it

Quick start (from repo root):

```bash
# Pull models
make ollama-pull-fast          # llama3.1:8b, fast dev model (~5GB)
make ollama-pull-dev           # gemma4:e4b, stronger dev model (~9GB)
make ollama-pull-quality       # gemma4:26b, quality model (~26GB)

# Start local Ollama runtime with keep-alive enabled
make ollama-serve
```

On macOS, prefer native Ollama install for local development. Docker Desktop does not provide GPU passthrough for Ollama on macOS, so containerized local runs are typically much slower and are not the recommended default.

For Ollama, SimBoard accepts `ASSISTANT_OLLAMA_BASE_URL=http://localhost:11434` and normalizes it to Ollama's OpenAI-compatible `/v1` endpoint internally. `ASSISTANT_OLLAMA_API_KEY` is optional for local runs and can stay blank unless a proxy in front of Ollama requires auth.

For LivAI, `ASSISTANT_LIVAI_*` names are canonical.
For the current LivAI OpenAI-compatible chat path, SimBoard omits `temperature` for `gpt-5*` models because that endpoint rejects the parameter.
For step-by-step local setup and provider examples, see [docs/developer/README.md](../docs/developer/README.md#assistant-llm-env-setup).

For repo-wide setup and contributor workflow, see [docs/developer/README.md](../docs/developer/README.md).
