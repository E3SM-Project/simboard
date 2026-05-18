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
- `ASSISTANT_LLM_PROVIDER` with `openai`, `anthropic`, or `livai`
- `ASSISTANT_OPENAI_API_KEY` / `ASSISTANT_OPENAI_MODEL`
- `ASSISTANT_ANTHROPIC_API_KEY` / `ASSISTANT_ANTHROPIC_MODEL`
- `ASSISTANT_LIVAI_API_KEY` / `ASSISTANT_LIVAI_MODEL` / `ASSISTANT_LIVAI_BASE_URL`
- `ASSISTANT_LLM_TIMEOUT_SECONDS`
- `ASSISTANT_LLM_TEMPERATURE`
- `ASSISTANT_LLM_MAX_TOKENS`
- `ASSISTANT_SNAPSHOT_MAX_CHARS`

For LivAI, `ASSISTANT_LIVAI_*` names are canonical. Legacy aliases `LIVAI_API_KEY` and `LIVAI_BASE_URL` are still accepted for backward compatibility.
For step-by-step local setup and provider examples, see [docs/developer/README.md](../docs/developer/README.md#assistant-llm-env-setup).

For repo-wide setup and contributor workflow, see [docs/developer/README.md](../docs/developer/README.md).
