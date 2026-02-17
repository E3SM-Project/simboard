# SimBoard Project Instructions

See @README.md for general project overview, @frontend/README.md for frontend architecture, and @backend/README.md for backend details.

## Architecture Overview

**Monorepo structure:**
- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React + Vite + Tailwind + shadcn
- **Feature-based isolation**: No direct cross-feature imports (enforced by ESLint boundaries)
- **Local HTTPS**: Both services use dev SSL certs from `certs/`

## Essential Commands

**Setup (first time):**
```bash
make install              # Install all dependencies
make setup-local          # Create env files, certs, DB, migrations, seed data
```

**Development workflow:**
```bash
make backend-run          # Start backend at https://127.0.0.1:8000/docs
make frontend-run         # Start frontend at https://127.0.0.1:5173
```

**Testing & Linting:**
```bash
make backend-test         # Run pytest
make frontend-lint        # ESLint
make frontend-fix         # Auto-fix ESLint issues
make pre-commit-run       # Run all pre-commit hooks (MUST run from repo root)
```

**Database migrations:**
```bash
make backend-migrate m='your migration message'
make backend-upgrade
```

**Troubleshooting:**
```bash
make setup-local-assets   # Fix missing env errors
make gen-certs            # Regenerate SSL certs
```

## Code Conventions

**Backend:**
- Use `uv` for Python environment management (NOT pip/venv)
- Domain logic in `backend/app/features/*`
- Database models in `backend/app/models/`
- New endpoints: add to `backend/app/api/yourfeature.py` and register in `main.py`

**Frontend:**
- Feature modules in `frontend/src/features/*` (isolated, no cross-feature imports)
- Shared UI components in `components/shared/`
- API logic in `features/yourfeature/api/`
- Hooks in `features/yourfeature/hooks/`
- **IMPORTANT**: ESLint architectural boundaries are ENFORCED - respect layer rules

**Environment variables:**
- Store secrets in `.envs/local/*.env` (gitignored)
- Templates in `.envs/example/*.env` (committed)

## Workflow Rules

**Pre-commit hooks:**
- ALWAYS run from repo root, never from subfolders
- Use `make pre-commit-run` or `cd backend && uv run pre-commit run --all-files`

**Development mode:**
- Bare-metal recommended for hot reload: `make backend-run` + `make frontend-run`
- Docker alternative: `docker compose -f docker-compose.local.yml up --build`

**Testing:**
- Run backend tests after any backend changes: `make backend-test`
- Prefer running single tests for performance when possible

**Linting:**
- Backend: `make backend-clean && make backend-run` (includes linting + hot reload)
- Frontend: `make frontend-lint` then `make frontend-fix` to auto-fix

## Integration Points

- **GitHub OAuth**: Configure in `.envs/local/backend.env`
- **PostgreSQL**: Used for backend DB (config in env files)
- **Pre-commit**: Python hooks via `uv`, frontend hooks via `pnpm`

## Common Pitfalls

- Don't run pre-commit from subfolders - always from repo root
- If missing env errors occur, run `make setup-local-assets`
- SSL issues: regenerate with `make gen-certs`
- Backend uses `uv` not pip/venv - use `uv` commands
- Frontend architectural boundaries are enforced - check `frontend/README.md` for layer rules

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
make lint && make frontend-lint && make backend-test && make pre-commit-run
```
