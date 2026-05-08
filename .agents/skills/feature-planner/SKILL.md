---
name: feature-planner
description: Turn SimBoard product or engineering requests into concrete implementation plans scoped to the repo's backend, frontend, testing, docs, and workflow constraints.
---

# Feature Planner

## Overview

Turn a request into an executable SimBoard plan. Produce scoped implementation steps, affected modules, validation, and risks without drifting into code or durable user docs.

## Use When

- The request spans backend, frontend, docs, or multiple features
- The user wants a plan before implementation
- The work needs decomposition into reviewable steps

## Workflow

1. Inspect the relevant features, routes, APIs, and tests before planning.
2. Scope the request against the existing monorepo structure and feature boundaries.
3. Name the concrete files, modules, and commands likely to change.
4. Call out backend, frontend, tests, docs, migrations, and rollout implications.
5. State open questions, assumptions, and validation commands.

## Repo Rules

- Plan in terms of the existing split across `backend/`, `frontend/`, and `docs/`.
- Respect backend feature modules under `backend/app/features/*`.
- Respect frontend feature isolation and route composition in `frontend/src/features/*` and `frontend/src/routes/routes.tsx`.
- Account for app-level shared state when relevant, especially data and compare selection threaded through `frontend/src/App.tsx`.
- Include router registration, schema/model changes, and Alembic work when backend contracts or persistence change.
- Include README or docs updates when developer workflows or user-facing behavior change.
- Prefer repo commands such as `make backend-test`, `make frontend-lint`, `pnpm --dir frontend run type-check`, and `make pre-commit-run`.

## Guardrails

- Do not invent new architecture layers or dependency additions without strong repo evidence.
- Do not ignore auth, role, migration, or environment impacts for upload, ingestion, or token work.
- Do not produce a generic checklist with no file or module specificity.
