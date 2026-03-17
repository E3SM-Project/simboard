---
name: feature-planner
description: Turn SimBoard product or engineering requests into concrete implementation plans scoped to the repo's backend, frontend, testing, docs, and workflow constraints.
---

# Feature Planner

## Purpose

Convert a request into an executable SimBoard implementation plan. Produce scope, sequencing, and risk analysis, not durable human documentation and not production code.

## When To Use

- A request is ambiguous or spans multiple parts of the monorepo
- The user wants a concrete execution plan before implementation
- A feature may affect backend APIs, frontend routes, auth, migrations, or docs
- The work needs decomposition into PR-sized steps

## Inputs Expected

- The feature or problem statement
- Target users or workflows
- Any constraints on scope, timing, dependencies, or rollout
- Known affected areas in backend, frontend, docs, or deployment

## Outputs Required

- A scoped implementation plan with phases or milestones
- Expected files/directories or modules to touch
- Backend, frontend, test, and docs impacts
- Risks, open questions, and assumptions
- Recommended validation commands and rollout order

## Repo-Specific Conventions

- Plan in terms of the existing monorepo split: `backend/`, `frontend/`, and `docs/`.
- Respect the frontend feature-boundary rules and route composition model.
- Respect the backend feature modules under `backend/app/features/*`.
- Call out router registration, schema/model changes, and Alembic migrations when backend contracts or persistence change.
- If a change affects developer setup or behavior, include README/docs updates in the plan.
- Prefer repo commands and make targets in the execution plan rather than ad hoc shell steps.
- Treat pre-commit, backend tests, frontend linting, and type-checking as part of the definition of done.

## Constraints / Anti-Patterns

- Do not drift into writing durable docs for humans; that belongs to `docs-writer`.
- Do not drift into implementation details that assume code already exists when it does not.
- Do not invent new architecture layers or service splits without strong evidence from the repo.
- Do not ignore auth, role, migration, or environment impacts for features that touch upload, tokens, or ingestion.
- Do not produce a generic checklist with no file/module specificity.

## Example Task

Plan a feature that lets users save and revisit comparison sets by outlining required backend persistence changes, frontend route/state updates, test coverage, migration needs, and README/docs follow-up before anyone writes code.
