# SimBoard — Claude Instructions

> **Canonical source:** [`AGENTS.md`](../AGENTS.md) is the single source of truth for AI development rules.
> This file is a derived summary for Claude Code and Claude-based tools. It must align with `AGENTS.md` and must not hardcode volatile configuration values (versions, counts, CI matrix values).

See `README.md` for the full project overview, `frontend/README.md` for frontend architecture, and `backend/README.md` for backend details.

## Architecture

- **Monorepo** with `backend/` (FastAPI, SQLAlchemy, Alembic) and `frontend/` (React, Vite, Tailwind, shadcn).
- **Feature-based organization**:
  - Backend domain logic in `backend/app/features/*/`, models in `backend/app/models/`, API routes in `backend/app/api/`.
  - Frontend modules in `frontend/src/features/*/`, shared UI in `frontend/src/components/shared/`.
- **Frontend isolation**: No direct cross-feature imports — enforced by `eslint-plugin-boundaries`.
- **Local HTTPS**: Dev SSL certs in `certs/`.

## Coding Standards

**Backend (Python):**
- Use `uv` for environment management (NOT pip/venv).
- Linting/formatting: Ruff. Type checking: mypy. Config in `pyproject.toml`.
- New endpoints in `backend/app/api/`, registered in `main.py`.
- Migrations via Alembic: `make backend-migrate m='msg'` then `make backend-upgrade`.

**Frontend (TypeScript):**
- Use `pnpm` for dependency management.
- ESLint (with architectural boundaries) + Prettier.
- API logic in `features/*/api/`, hooks in `features/*/hooks/`.
- Shared UI in `components/shared/` — must be genuinely reusable.

**Environment:**
- Secrets in `.envs/local/*.env` (gitignored); templates in `.envs/example/*.env` (committed).

## Essential Commands

```bash
make install          # Install all dependencies
make setup-local      # Setup env files, certs, DB, migrations, seed
make backend-run      # Start backend with hot reload
make frontend-run     # Start frontend with hot reload
make backend-test     # Run backend tests (pytest)
make frontend-lint    # Lint frontend (ESLint)
make frontend-fix     # Auto-fix frontend lint issues
make pre-commit-run   # Run all pre-commit hooks (from repo root)
make gen-certs        # Regenerate SSL certificates
make setup-local-assets  # Fix missing env errors
```

## Rules

- Always run pre-commit from the **repository root**, never from subdirectories.
- Frontend features must not import from other features.
- Pull requests should include tests and documentation updates where applicable.
- Do not hardcode dependency versions or CI configuration in instruction files.
- Refer to `pyproject.toml`, `package.json`, and `.pre-commit-config.yaml` for current tool versions.

## Integration Points

- **GitHub OAuth**: Configured in `.envs/local/backend.env`.
- **PostgreSQL**: Primary backend database (config via env variables).
- **Pre-commit**: Python hooks via `uv`, frontend hooks via `pnpm`.
- **CI/CD**: GitHub Actions in `.github/workflows/`.
- **Deployment**: NERSC Spin — see `docs/cicd/DEPLOYMENT.md`.

## Common Pitfalls

- Don't run pre-commit from subdirectories — always from repo root.
- Missing env errors → run `make setup-local-assets`.
- SSL issues → regenerate with `make gen-certs`.
- Backend uses `uv` not pip/venv — always use `uv` commands.
- Frontend architectural boundaries are enforced — check `frontend/README.md` for layer rules.

## Quick Examples

**Add backend feature:**
1. Create in `backend/app/features/yourfeature/`
2. Add API endpoints in `backend/app/api/yourfeature.py`
3. Register routes in `main.py`
4. Create migration: `make backend-migrate m='add yourfeature'`
5. Apply migration: `make backend-upgrade`
6. Test: `make backend-test`

**Add frontend feature:**
1. Create in `frontend/src/features/yourfeature/`
2. Add API logic in `features/yourfeature/api/`
3. Add hooks in `features/yourfeature/hooks/`
4. Use shared UI from `components/shared/`
5. Lint: `make frontend-lint && make frontend-fix`

**Run all checks before committing:**
```bash
make backend-test && make frontend-lint && make pre-commit-run
```
