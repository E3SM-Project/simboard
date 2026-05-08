<p align="center">
  <span style="display:inline-block; background:#ffffff; padding:16px 24px; border-radius:12px;">
    <img src="frontend/public/logos/simboard-logo-full-white-bg.png" alt="SimBoard logo" width="360" />
  </span>
</p>

# SimBoard

## Overview

SimBoard is an E3SM-focused catalog for simulation metadata. It turns simulation archives and run metadata into a browsable, comparable record of cases, executions, provenance, and related artifacts.

## Why SimBoard Exists

SimBoard exists so researchers and maintainers do not have to reconstruct simulation context from raw files, ad hoc notes, and scattered links. The repository is centered on simulation metadata, comparison, and provenance rather than raw model output serving.

## Current Capabilities

- ingest packaged simulation archives into normalized case and simulation records
- browse runs and cases from the UI
- view case details, simulation details, artifacts, and external links
- compare selected simulations side by side
- preserve provenance such as machine, Git metadata, HPC username, artifacts, and external links
- resolve PACE experiment links from execution IDs
- support browser-based GitHub auth and service-account token auth for privileged automation

`TODO/VERIFY`: the frontend includes an AI comparison widget that posts to `/analyze-simulations`, but no matching backend route was found under `backend/app/`. Do not treat AI-assisted comparison as a supported feature until that endpoint exists.

## Technology At A Glance

- frontend: React, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS, shadcn/ui
- backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- database: PostgreSQL
- auth: GitHub OAuth for browser flows, API tokens for service accounts
- tooling: `uv`, `pnpm`, Ruff, mypy, ESLint, Prettier, pre-commit
- CI/CD: GitHub Actions plus NERSC-focused deployment/build docs under `docs/`

## Documentation Map

- Contributor guide: [docs/developer/README.md](docs/developer/README.md)
- Contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md)
- Backend details: [backend/README.md](backend/README.md)
- Frontend details: [frontend/README.md](frontend/README.md)
- Docs index: [docs/README.md](docs/README.md)
- CI/CD and deployment docs: [docs/cicd/README.md](docs/cicd/README.md)

## How to Contribute

Start with [CONTRIBUTING.md](CONTRIBUTING.md) for issue, branch, commit, PR, and validation expectations. If you are new to the repo, use the contributor guide at [docs/developer/README.md](docs/developer/README.md) for local setup, architecture, and development workflow.
