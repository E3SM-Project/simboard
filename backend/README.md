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

Backend env templates live in `.envs/example/backend.env.example`. Local developer values live in `.envs/local/backend.env`.

Restart the backend after changing local env values.

For repo-wide setup, assistant LLM configuration, and contributor workflow, see [docs/developer/README.md](../docs/developer/README.md).
