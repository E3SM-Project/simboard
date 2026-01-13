# SimBoard AI Coding Agent Instructions

This guide enables AI agents to work productively in the SimBoard monorepo. It summarizes architecture, workflows, and conventions unique to this project.

---

## Big Picture Architecture
- **Monorepo**: Contains `backend` (FastAPI, SQLAlchemy, Alembic) and `frontend` (React, Vite, Tailwind, shadcn).
- **Feature-based frontend**: `frontend/src/features/*` are isolated modules; no direct cross-feature imports. Shared UI in `components/shared`.
- **Backend**: REST API for simulation metadata, with domain logic in `backend/app/features/*` and database models in `backend/app/models/`.
- **Local HTTPS**: Both backend and frontend use dev SSL certs from `certs/`.

## Developer Workflows
- **Quickstart for Beginners:**
  1. Clone the repo: `git clone https://github.com/E3SM-Project/simboard.git && cd simboard`
  2. Install dependencies: `make install` (sets up backend, frontend, and pre-commit)
  3. Prepare local environment: `make setup-local` (creates env files, certs, DB, runs migrations and seeds)
  4. Start backend: `make backend-run` (serves API at https://127.0.0.1:8000/docs)
  5. Start frontend: `make frontend-run` (serves UI at https://127.0.0.1:5173)
  6. Run all checks: `make lint && make frontend-lint && make backend-test && make pre-commit-run`
  7. For Docker: `docker compose -f docker-compose.local.yml up --build`

**Common troubleshooting:**
- If you see missing env errors, run `make setup-local-assets`.
- For SSL issues, regenerate certs with `make gen-certs`.
- Always run pre-commit from repo root, not subfolders.
- **Bare-metal dev (recommended):**
  1. `make setup-local` (env files, certs, DB, migrations, seed)
  2. `make backend-run` (backend hot reload)
  3. `make frontend-run` (frontend hot reload)
- **Docker dev:** Use `docker-compose.local.yml` for local multi-service setup.
- **Pre-commit hooks:** Always run from repo root. Use `make pre-commit-run` or `cd backend && uv run pre-commit run --all-files`.
- **Testing:**
  - Backend: `make backend-test` (pytest)
  - Frontend: See `frontend/README.md` for details
- **Linting/Type-check:**
  - Backend: `make backend-clean && make backend-run` for linting and hot reload
  - Frontend: `make frontend-lint` (ESLint), `make frontend-fix` (auto-fix), Prettier via pre-commit

## Project-Specific Conventions
- **Frontend architectural boundaries** enforced by ESLint (`eslint-plugin-boundaries`). See `frontend/README.md` for layer rules.
- **Backend uses `uv` for Python env management** (not pip/venv).
- **Environment variables**: Store in `.envs/local/*.env` (ignored), templates in `.envs/example/*.env` (committed).
- **Database migrations**: Alembic via `make backend-migrate m='msg'` and `make backend-upgrade`.
- **Local HTTPS**: Generate certs with `make gen-certs`.

## Integration Points & External Dependencies
- **GitHub OAuth**: Configure in `.envs/local/backend.env`.
- **PostgreSQL**: Used for backend DB, configured in env files and CI.
- **Pre-commit**: Python hooks via `uv`, frontend hooks via `pnpm`.
- **Docker/NERSC Spin**: Build/push images using `docker buildx` (see README for commands).

## Key Files & Directories
- `Makefile`: Unified automation for setup, build, test, lint, certs, etc.
- `backend/app/features/`, `backend/app/models/`: Domain logic and DB models
- `frontend/src/features/`, `frontend/src/components/shared/`: Feature modules and shared UI
- `.envs/`: Environment configs
- `certs/`: Local SSL certs
- `.pre-commit-config.yaml`: Pre-commit hook config
- `.github/workflows/backend-ci.yml`: CI for backend

## Examples
- **Backend API development:**
  - Add new endpoints in `backend/app/api/yourfeature.py` and register them in `main.py`.
  - Use `make backend-migrate m='your message'` to create DB migrations, then `make backend-upgrade` to apply.
  - Run backend tests: `make backend-test`.
- **Frontend feature development:**
  - Create a new feature in `frontend/src/features/yourfeature/`.
  - Add API logic in `features/yourfeature/api/` and hooks in `features/yourfeature/hooks/`.
  - Use shared UI from `components/shared/`.
  - Run frontend dev server: `make frontend-run`.
  - Lint and auto-fix: `make frontend-lint` and `make frontend-fix`.
- **Environment management:**
  - Copy example env files: `make copy-env-files`.
  - Edit `.envs/local/backend.env` and `.envs/local/frontend.env` for secrets and local config.
- **Pre-commit usage:**
  - Install hooks: `make pre-commit-install`
  - Run checks: `make pre-commit-run`
  - Skip checks (not recommended): `git commit --no-verify`
- **Add a backend feature**: Place in `backend/app/features/yourfeature/`, update API in `api/` subdir.
- **Add a frontend feature**: Place in `frontend/src/features/yourfeature/`, keep API logic in `features/*/api` and hooks in `features/*/hooks`.
- **Run all checks**: `make lint && make type-check && make test && make pre-commit-run`

---

For more, see [README.md](../../README.md) and feature-specific docs in `frontend/README.md` and `backend/README.md`.
