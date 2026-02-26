# SimBoard — Copilot Instructions

> **Canonical source:** [`AGENTS.md`](../AGENTS.md) is the single source of truth for AI development rules.
> This file is a derived summary for GitHub Copilot Chat. It must align with `AGENTS.md` and must not hardcode volatile configuration values (versions, counts, CI matrix values).

---

## Architecture

- **Monorepo** with `backend/` (FastAPI, SQLAlchemy, Alembic) and `frontend/` (React, Vite, Tailwind, shadcn).
- **Feature-based organization**: Backend logic in `backend/app/features/*/`, frontend modules in `frontend/src/features/*/`.
- **Frontend isolation**: No direct cross-feature imports — enforced by `eslint-plugin-boundaries`. See `frontend/README.md` for layer rules.
- **Local HTTPS**: Dev SSL certs in `certs/`.

## Coding Standards

**Backend (Python):**
- Use `uv` for environment management (not pip/venv).
- Linting/formatting: Ruff. Type checking: mypy. Config in `pyproject.toml`.
- New endpoints in `backend/app/api/`, registered in `main.py`.
- Migrations: `make backend-migrate m='msg'` then `make backend-upgrade`.

**Frontend (TypeScript):**
- Use `pnpm` for dependency management.
- ESLint (with architectural boundaries) + Prettier.
- API logic in `features/*/api/`, hooks in `features/*/hooks/`, shared UI in `components/shared/`.

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
```

## Rules

- Always run pre-commit from the **repository root**, never from subdirectories.
- Frontend features must not import from other features.
- Pull requests should include tests and documentation updates where applicable.
- Do not hardcode dependency versions or CI configuration in instruction files.
- Refer to `pyproject.toml`, `package.json`, and `.pre-commit-config.yaml` for current tool versions.

## Common Pitfalls

- Missing env errors → `make setup-local-assets`
- SSL issues → `make gen-certs`
- Wrong package manager: backend uses `uv`, frontend uses `pnpm`
- Pre-commit failures from subdirectories — always run from repo root

## References

- Project overview: `README.md`
- Backend details: `backend/README.md`
- Frontend architecture: `frontend/README.md`
- Deployment: `docs/cicd/DEPLOYMENT.md`
- Full AI rules: `AGENTS.md`
