<p align="center">
  <span style="display:inline-block; background:#ffffff; padding:16px 24px; border-radius:12px;">
    <img src="frontend/public/logos/simboard-logo-full-white-bg.png" alt="SimBoard logo" width="360" />
  </span>
</p>

<p align="center">
  <a href="https://github.com/E3SM-Project/simboard/actions/workflows/build-backend-dev.yml"><img src="https://github.com/E3SM-Project/simboard/actions/workflows/build-backend-dev.yml/badge.svg" alt="Backend CI"></a>
  <a href="https://github.com/E3SM-Project/simboard/actions/workflows/build-frontend-dev.yml"><img src="https://github.com/E3SM-Project/simboard/actions/workflows/build-frontend-dev.yml/badge.svg" alt="Frontend CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
</p>

## Overview

SimBoard is an E3SM-focused catalog for simulation metadata. It turns simulation archives and run metadata into a browsable, comparable record of cases, executions, provenance, and related artifacts.

## Why SimBoard Exists

SimBoard exists so researchers and maintainers do not have to reconstruct simulation context from raw files, ad hoc notes, and scattered links. The repository is centered on simulation metadata, comparison, and provenance rather than raw model output serving.

## Current Capabilities

- Ingest packaged simulation archives into normalized case and simulation records
- Browse runs and cases from the UI
- View case details, simulation details, artifacts, and external links
- Compare selected simulations side by side
- Preserve provenance such as machine, Git metadata, HPC username, artifacts, and external links
- Resolve PACE experiment links from execution IDs
- Support browser-based GitHub auth and service-account token auth for privileged automation

## System Summary

SimBoard is organized as a React frontend, a FastAPI backend, and PostgreSQL-backed persistence. Together they handle metadata ingestion, normalization, browsing, comparison, provenance, and authenticated upload workflows.

For architecture diagrams, API/data-flow detail, and contributor-oriented system context, see [docs/developer/README.md](docs/developer/README.md).

## Technology At A Glance

- Frontend: React, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS, shadcn/ui
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- Database: PostgreSQL
- Auth: GitHub OAuth for browser flows, API tokens for service accounts
- Tooling: `uv`, `pnpm`, `ruff`, `mypy`, `eslint`, `prettier`, `pre-commit`
- CI/CD: GitHub Actions plus NERSC-focused deployment/build docs under `docs/`

## Documentation Map

- Hosted docs: <https://simboard.readthedocs.io/>
- Local docs preview: `make docs-serve`
- Contributor guide: [docs/developer/README.md](docs/developer/README.md)
- Contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md)
- Backend details: [backend/README.md](backend/README.md)
- Frontend details: [frontend/README.md](frontend/README.md)
- Docs index: [docs/README.md](docs/README.md)
- CI/CD and deployment docs: [docs/cicd/README.md](docs/cicd/README.md)

## How to Contribute

Start with [CONTRIBUTING.md](CONTRIBUTING.md) for issue, branch, commit, PR, and validation expectations. If you are new to the repo, use the contributor guide at [docs/developer/README.md](docs/developer/README.md) for local setup, architecture, and development workflow.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
