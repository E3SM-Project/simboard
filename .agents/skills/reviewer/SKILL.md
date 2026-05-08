---
name: reviewer
description: Review SimBoard changes for correctness, maintainability, architecture fit, regression risk, and adherence to the repo's FastAPI, SQLAlchemy, React, and feature-boundary conventions.
---

# Reviewer

## Overview

Review SimBoard changes with a code-review mindset. Prioritize correctness, architecture fit, regression risk, API compatibility, and missing validation over style.

## Use When

- Reviewing a branch, diff, or PR before merge
- Auditing whether a change fits SimBoard backend or frontend architecture
- Checking whether work needs tests, docs, migrations, or follow-up cleanup

## Workflow

1. Inspect the diff and the surrounding code before judging the change.
2. Check correctness first: behavior, failure modes, auth, contracts, and persistence.
3. Check repo fit next: feature boundaries, router registration, model imports, and shared state patterns.
4. Check validation coverage: tests, lint, type-check, docs, migrations, and seed impacts.
5. Report prioritized findings first, with file references and concrete risk.

## Repo Rules

- Treat the repo `AGENTS.md` as policy, but prefer current code when stale prose conflicts with implementation details.
- Backend work should stay within `backend/app/features/*`, `backend/app/common/*`, and `backend/app/core/*`, with tests under `backend/tests/*`.
- Review API contract drift carefully because frontend payloads generally expect camelCase schemas.
- Frontend work must respect `frontend/eslint.config.js` boundaries and current route composition in `frontend/src/routes/routes.tsx`.
- When reviewing frontend behavior, account for shared selection and top-level data ownership in `frontend/src/App.tsx`.
- Validation should match repo workflows such as `make backend-test`, `make frontend-lint`, `pnpm --dir frontend run type-check`, and `make pre-commit-run`.

## Guardrails

- Do not lead with summaries; findings come first.
- Do not waive missing migrations, router registration, model imports, or boundary violations.
- Do not review only happy paths; check empty states, error paths, role checks, and compatibility.
- Do not recommend large refactors unless the design itself is the bug.
