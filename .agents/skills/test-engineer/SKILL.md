---
name: test-engineer
description: Add or improve SimBoard automated tests and validation coverage, prioritizing deterministic backend pytest coverage and practical regression reduction over speculative tooling.
---

# Test Engineer

## Purpose

Reduce regression risk in SimBoard by adding or tightening automated checks that match the repo's current testing setup.

## When To Use

- After backend behavior changes, bug fixes, or schema/API contract changes
- When parser, ingestion, auth, or role logic is modified
- When a review identifies missing regression coverage
- When a change needs validation strategy, even if only part of it can be automated today

## Inputs Expected

- The behavior being changed or protected
- The files touched and likely failure modes
- Existing tests in the same feature area
- The intended validation scope and any constraints on adding new tooling

## Outputs Required

- Deterministic automated tests where the repo already supports them
- Clear note of what was validated and what remains uncovered
- Minimal test-only helpers or fixtures when necessary
- Commands run and their outcomes

## Repo-Specific Conventions

- Backend tests live under `backend/tests/**`, generally mirroring feature areas such as `backend/tests/features/simulation/` or `backend/tests/features/ingestion/`.
- Reuse fixtures from `backend/tests/conftest.py` before inventing new database setup.
- Prefer focused API, schema, parser, or model tests over broad end-to-end flows.
- Backend tests should work with the existing PostgreSQL + Alembic test setup and dependency overrides.
- Frontend currently has linting and type-checking, but no established unit/e2e test harness in the repo. For frontend-only work, use `make frontend-lint` and `pnpm --dir frontend run type-check` as the baseline unless the user explicitly wants new testing infrastructure.
- If frontend behavior depends on backend contracts, prefer strengthening backend tests around the contract rather than introducing a brand-new frontend test stack.
- Use repo commands such as `make backend-test`, `make frontend-lint`, and `make pre-commit-run` from the repository root.

## Constraints / Anti-Patterns

- Do not add flaky tests that depend on wall-clock timing, external networks, GitHub OAuth, or mutable remote state.
- Do not introduce Vitest, Playwright, Cypress, or similar tools as part of routine work unless the user asks or the repo adds them.
- Do not overuse broad integration tests when a targeted parser/API/schema test would cover the behavior more reliably.
- Do not leave important backend behavior validated only by manual steps if pytest coverage is practical.
- Do not duplicate fixture logic that already exists in `backend/tests/conftest.py`.

## Example Task

Add regression coverage for a change in token revocation by updating `backend/tests/features/user/api/test_token.py`, reusing existing auth fixtures, and running `make backend-test` to verify the API behavior remains stable.
