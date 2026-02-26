# AGENTS.md — Canonical AI Development Rules

> **This file is the single source of truth** for AI-assisted development in the SimBoard repository.
> Tool-specific files (`.github/copilot-instructions.md`, `.claude/CLAUDE.md`) are derived from this document.

---

## Anti-Drift Policy

AI instruction files must **not** hardcode volatile configuration values such as:

- Exact dependency versions or version constraints
- CI matrix versions or tool configuration values
- Counts of modules, drivers, or files
- Experimental feature status

When such values are needed, reference the authoritative source:

- `pyproject.toml` — Python dependencies and tool settings
- `.pre-commit-config.yaml` — Pre-commit hook configuration
- `.github/workflows/` — CI/CD pipeline definitions
- Source code defaults — Runtime configuration

Instruction files should be **structural** (architectural patterns, capability-based descriptions, policy-level constraints) rather than **quantitative** (numeric counts, dynamic file listings, version strings).

All tool-specific files must remain valid if dependency versions or CI settings change, and must be safely regenerable without manual editing.

---

## Architecture

### Monorepo Structure

SimBoard is a monorepo containing two primary services:

- **Backend** (`backend/`) — FastAPI REST API with SQLAlchemy ORM and Alembic migrations, using PostgreSQL as the primary database.
- **Frontend** (`frontend/`) — React single-page application built with Vite, styled with Tailwind CSS and shadcn components.

### Feature-Based Organization

Both services follow **feature-based architecture**:

- **Backend**: Domain logic in `backend/app/features/*/`, database models in `backend/app/models/`, API routes in `backend/app/api/`.
- **Frontend**: Feature modules in `frontend/src/features/*/` with API logic in `features/*/api/` and hooks in `features/*/hooks/`. Shared UI in `frontend/src/components/shared/`.

### Architectural Boundaries

- **Frontend features are isolated**: No direct cross-feature imports. Enforced by `eslint-plugin-boundaries`. See `frontend/README.md` for layer rules.
- **Backend features are modular**: Each feature has its own directory under `backend/app/features/`.

---

## Coding Standards

### Backend (Python / FastAPI)

- Use **`uv`** for Python environment management — never `pip` or `venv` directly.
- Follow linting and formatting rules defined in `pyproject.toml` (Ruff for linting/formatting, mypy for type checking).
- New endpoints go in `backend/app/api/` and are registered in `main.py`.
- Database migrations use Alembic: `make backend-migrate m='message'` then `make backend-upgrade`.
- Environment variables are loaded from `.envs/local/*.env` (gitignored); templates live in `.envs/example/*.env` (committed).

### Frontend (TypeScript / React)

- Use **`pnpm`** for dependency management.
- Follow ESLint rules (including architectural boundary enforcement) and Prettier formatting.
- Feature modules must not import from other features directly.
- Shared components must be genuinely reusable and placed in `components/shared/`.
- API logic lives under `features/*/api/`; hooks under `features/*/hooks/`.

---

## Testing

- **Backend**: Run tests with `make backend-test` (pytest). Always run tests after backend changes.
- **Frontend**: Run linting with `make frontend-lint`; auto-fix with `make frontend-fix`.
- **Pre-commit hooks**: Always run from the **repository root**, not from subdirectories. Use `make pre-commit-run`.
- Pull requests should include tests and documentation updates where applicable.

---

## Development Workflow

### Setup

```bash
make install          # Install all dependencies (backend, frontend, pre-commit)
make setup-local      # Create env files, certs, DB, migrations, seed data
```

### Daily Development

```bash
make backend-run      # Start backend with hot reload
make frontend-run     # Start frontend with hot reload
```

### Checks Before Committing

```bash
make backend-test     # Run backend tests
make frontend-lint    # Lint frontend
make pre-commit-run   # Run all pre-commit hooks
```

### Docker Alternative

```bash
docker compose -f docker-compose.local.yml up --build
```

---

## Dependency Policy

- Backend dependencies are declared in `backend/pyproject.toml` and locked in `backend/uv.lock`.
- Frontend dependencies are declared in `frontend/package.json` and locked in `frontend/pnpm-lock.yaml`.
- Do not add dependencies without verifying they are necessary.
- Refer to lockfiles and manifests for current versions — never hardcode versions in documentation or instruction files.

---

## Integration Points

- **GitHub OAuth**: Configured via environment variables in `.envs/local/backend.env`.
- **PostgreSQL**: Primary backend database, configured through environment variables.
- **Local HTTPS**: Both services use dev SSL certificates from `certs/`. Regenerate with `make gen-certs`.
- **CI/CD**: GitHub Actions workflows in `.github/workflows/` handle automated builds and deployments.
- **NERSC Spin**: Production deployment target. See `docs/cicd/DEPLOYMENT.md` for details.

---

## Key References

| Topic | File |
|---|---|
| Project overview | `README.md` |
| Backend details | `backend/README.md` |
| Frontend architecture | `frontend/README.md` |
| CI/CD & deployment | `docs/cicd/DEPLOYMENT.md` |
| Python tooling config | `backend/pyproject.toml` |
| Pre-commit hooks | `.pre-commit-config.yaml` |
| Makefile targets | `make help` |

---

## Common Pitfalls

- **Pre-commit from subdirectories**: Always run from repo root. Some hooks depend on root-relative paths.
- **Missing env errors**: Run `make setup-local-assets` to regenerate environment files.
- **SSL issues**: Regenerate certificates with `make gen-certs`.
- **Wrong package manager**: Backend uses `uv`, not pip. Frontend uses `pnpm`, not npm/yarn.
- **Cross-feature imports**: Frontend features must not import from other features. ESLint will flag violations.
