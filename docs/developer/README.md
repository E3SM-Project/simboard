# Developer Guide

Use this guide for local setup, repo-wide development workflow, and contributor-oriented architecture. For service-specific
detail, see [backend/README.md](../backend/README.md) and [frontend/README.md](../frontend/README.md).

## System Overview

SimBoard is a web application for cataloging, browsing, comparing, and analyzing E3SM simulation metadata. The frontend, backend, and PostgreSQL database are hosted on NERSC Spin. Automated collection jobs running on HPC sites scan E3SM staging performance directories and submit changed case metadata to SimBoard for ingestion.

```mermaid
flowchart LR
  user[Browser User]
   ingest([Automated Collection])

  subgraph mono[SimBoard — hosted on NERSC Spin]
    direction LR
    fe[Frontend\nReact + Vite SPA]
    be[Backend\nFastAPI /api/v1]
    db[(PostgreSQL)]
  end

  gh[GitHub OAuth]
  pace[PACE Lookup]

  user --> fe
  fe -- HTTPS + cookie auth --> be
  ingest --> be
  be --> db
  be --> gh
  be --> pace
```

| Component            | Role                                                                                                                                                                         |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend             | Provides browse, detail, compare, authentication, and upload views. Calls the backend over HTTPS through `frontend/src/api/api.ts` with credentials enabled for cookie auth. |
| Backend              | Parses ingested archives, validates metadata, persists normalized records including per-run `CASE_HASH` grouping metadata, and exposes `/api/v1` endpoints.                  |
| PostgreSQL           | Stores cases, simulations, machines, users, tokens, artifacts, links, and ingestion records.                                                                                 |
| Automated collection | Runs on supported HPC sites, scans E3SM staging performance directories, and submits changed case metadata to SimBoard ingestion routes.                                     |
| External services    | GitHub OAuth for login and PACE for performance lookup.                                                                                                                      |

### Deployed API Base URLs

The backend is served from a dedicated `-api` subdomain, separate from the
frontend origin. The route prefix is `/api/v1` (`API_BASE` in
`backend/app/api/version.py`); the frontend resolves the origin from the
`VITE_API_BASE_URL` build variable (`frontend/src/api/api.ts`).

| Environment | Frontend                         | API base URL                               |
| ----------- | -------------------------------- | ------------------------------------------ |
| Dev         | `https://simboard-dev.e3sm.org/` | `https://simboard-dev-api.e3sm.org/api/v1` |
| Prod        | `https://simboard.e3sm.org/`     | `https://simboard-api.e3sm.org/api/v1`     |

- OpenAPI schema: `/openapi.json`
- Interactive docs (Swagger UI): `/docs`

Requests to the frontend origin under `/api/...` return `404`; clients must use
the `-api` subdomain. Locally the backend serves both the API and `/docs` on the
same origin (see [Local Environment Setup](#local-environment-setup)).

## Metadata Ingestion

In these docs, collection means site-side scanning and discovery of submission-qualified case directories, while ingestion means SimBoard API and database uptake of that collected metadata.

SimBoard supports local path ingestion from NERSC / Perlmutter and remote automated uploads from other DOE sites. Automated runners use database-backed stored known execution IDs during collection and submit submission-qualified case directories through ingestion API routes.

See [Metadata Ingestion Architecture](../architecture/metadata-ingestion.md) for terminology, ingestion modes, submission-state flow, runner configuration, site mapping, and PACE reference scripts.

## Local Environment Setup

Prerequisites:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or compatible local Docker runtime
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — fast Python package manager (replaces pip/venv)
- [Node.js](https://nodejs.org/) and [`pnpm`](https://pnpm.io/installation) — JavaScript runtime and package manager

Recommended first-run flow from the repository root:

```bash
make setup-local
make backend-run
make frontend-run
```

Open:

- API docs: `https://127.0.0.1:8000/docs`
- UI: `https://127.0.0.1:5173`

What `make setup-local` does:

- copies `.envs/example/*` into `.envs/local/` if missing
- generates local TLS certs in `certs/`
- starts PostgreSQL from `docker-compose.local.yml`
- installs backend and frontend dependencies
- runs Alembic migrations
- seeds development data

Useful commands:

```bash
make backend-test          # run backend pytest suite
make frontend-lint         # lint frontend with ESLint
make pre-commit-run        # run all pre-commit hooks (formatting, linting, etc.)
pnpm --dir frontend run type-check  # TypeScript type checking (no Makefile wrapper yet)
make help                  # list all available Makefile targets
```

## Optional Local Services

### GitHub Auth Setup

If you need authenticated browser flows such as upload:

1. [Create a GitHub OAuth app](https://github.com/settings/developers) with homepage `https://127.0.0.1:5173`.
2. Set the callback URL to `https://127.0.0.1:8000/api/v1/auth/github/callback`.
3. Put the GitHub credentials in `.envs/local/backend.env`.
4. Restart `make backend-run`.

If you need admin-only local flows such as service-account or token provisioning:

```bash
make backend-create-admin
```

For token-based ingestion and service-account details, see [docs/hpc_api_token_authentication.md](../deploy/hpc-api-token-authentication.md).

### Assistant LLM Setup

SimBoard can generate LLM-backed summaries on the simulation details page. If LLM support is disabled or misconfigured, the backend falls back to the deterministic metadata summary.

See [Assistant LLM Setup](assistant-llm-setup.md) for Ollama and LivAI configuration, model choices, token-budget guidance, and fallback troubleshooting.

## Daily Development Workflow

Common tasks beyond the initial setup:

```bash
make backend-run                   # start backend with hot reload
make frontend-run                  # start frontend with hot reload
make backend-test                  # run full backend test suite
make backend-seed                  # seed the database with sample data
make backend-rollback-seed         # remove seeded data
make backend-upgrade               # apply pending Alembic migrations
make backend-downgrade rev=<rev>   # roll back to a specific Alembic revision
make backend-reset                 # recreate the backend venv and reinstall deps
make frontend-lint                 # lint frontend
make frontend-fix                  # lint frontend with auto-fix
make pre-commit-run                # run all pre-commit hooks
```

To reset the database completely, stop the backend, bring down the Docker container, remove the volume, then re-run setup:

```bash
docker compose -f docker-compose.local.yml down -v
make setup-local
```

To run a single backend test file or test function:

```bash
cd backend
uv run pytest tests/path/to/test_file.py
uv run pytest tests/path/to/test_file.py::test_function_name
```

## Change Walkthrough

### Backend example: add a new API field

1. **Read** the relevant feature code under `backend/app/features/` and the corresponding test file under `backend/tests/`.
2. **Edit** the schema, model, or endpoint as needed.
3. **Migrate** if the change touches the database schema:

   ```bash
   make backend-migrate m='add field_name to table_name'
   make backend-upgrade
   ```

4. **Test**:

   ```bash
   make backend-test
   ```

5. **Validate** with pre-commit before committing:

   ```bash
   make pre-commit-run
   ```

6. **Commit and push**, then open a PR per [CONTRIBUTING.md on GitHub](https://github.com/E3SM-Project/simboard/blob/main/CONTRIBUTING.md).

### Frontend example: update a feature component

1. **Read** the feature module under `frontend/src/features/` and its API/hooks directories.
2. **Edit** the component, hook, or API call.
3. **Lint and type-check**:

   ```bash
   make frontend-lint
   pnpm --dir frontend run type-check
   ```

4. **Validate** with pre-commit:

   ```bash
   make pre-commit-run
   ```

5. **Commit and push**, then open a PR.

Key rule: feature modules must not import from other feature modules. If you need to share code between features, move it to `frontend/src/components/shared/` or `frontend/src/lib/`.

## Troubleshooting

**Docker not running or port conflict**
`make setup-local` starts PostgreSQL via Docker Compose. If Docker Desktop is not running, or port 5432 is already in use, the setup will fail. Start Docker Desktop and stop any conflicting services first.

**Missing environment variables**
If the backend fails to start with config or env errors, regenerate the env files:

```bash
make setup-local-assets
```

This copies `.envs/example/*` into `.envs/local/` without overwriting existing files.

**SSL / certificate errors**
The backend and frontend use local TLS certs from `certs/`. If they are missing or expired, regenerate them:

```bash
make gen-certs
```

Your browser will show a self-signed certificate warning — this is expected for local development.

**`uv` or `pnpm` not found**
The backend uses `uv` (not pip) and the frontend uses `pnpm` (not npm/yarn). Both must be on your `PATH`. See the [Prerequisites](#local-environment-setup) section for install links.

**Pre-commit fails or gives inconsistent results**
Always run pre-commit from the repository root, not from `backend/` or `frontend/`. Some hooks (e.g., `mypy`) depend on root-relative config paths.

```bash
# correct
make pre-commit-run

# incorrect — may produce wrong results
cd backend && uv run pre-commit run --all-files
```

**Frontend ESLint error about cross-feature imports**
Feature modules under `frontend/src/features/*/` must not import from other features. This is enforced by `eslint-plugin-boundaries`. Move shared code to `frontend/src/components/shared/` or `frontend/src/lib/`.

**Database out of sync after pulling new changes**
If a teammate added a migration, apply it:

```bash
make backend-upgrade
```

If the schema diverged significantly, reset the database entirely:

```bash
docker compose -f docker-compose.local.yml down -v
make setup-local
```

## Contributing

See [CONTRIBUTING.md on GitHub](https://github.com/E3SM-Project/simboard/blob/main/CONTRIBUTING.md) for issue, branch, commit, and PR expectations.

Key habits for safe changes:

- read the touched feature before editing it
- keep frontend feature boundaries intact (`eslint-plugin-boundaries` enforces this)
- update backend tests when behavior changes
- add Alembic migrations when schema changes
- run `make pre-commit-run` from the repository root, not from subdirectories

## Related Documentation

- backend service detail: [backend/README.md](../backend/README.md)
- frontend service detail: [frontend/README.md](../frontend/README.md)
- docs index: [docs/README.md](../README.md)
- CI/CD and deployment docs: [docs/cicd/README.md](../cicd/README.md)
