---
name: test-engineer
description: Add or improve SimBoard automated tests and validation coverage, prioritizing deterministic backend pytest coverage and practical regression reduction over speculative tooling.
---

# Test Engineer

## Overview

Reduce regression risk in SimBoard by adding or tightening automated validation that matches the repo's existing test setup.

## Use When

- Backend behavior, schemas, parsers, auth, or ingestion logic changes
- A review identifies missing regression coverage
- A change needs a concrete validation strategy

## Workflow

1. Inspect the touched code and nearby tests before adding coverage.
2. Reuse existing fixtures and test patterns wherever possible.
3. Prefer focused API, schema, parser, or model tests over broad end-to-end coverage.
4. For frontend-only changes, use lint and type-check as the baseline unless the repo already has a tighter automated path for that area.
5. Report what was validated and what remains uncovered.

## Repo Rules

- Backend tests live under `backend/tests/**`, generally mirroring feature areas.
- Reuse fixtures from `backend/tests/conftest.py` before adding new setup helpers.
- Keep backend tests compatible with the existing PostgreSQL plus Alembic test flow.
- Frontend does not have an established unit or e2e harness in this repo; use `make frontend-lint` and `pnpm --dir frontend run type-check` as baseline validation for frontend-only work.
- If frontend behavior depends on backend contracts, prefer strengthening backend tests around the contract.
- Use repo commands such as `make backend-test`, `make frontend-lint`, and `make pre-commit-run` from the repo root.

## Guardrails

- Do not add flaky tests tied to wall-clock timing, external networks, OAuth round-trips, or mutable remote state.
- Do not introduce new frontend test frameworks as routine work.
- Do not duplicate fixture logic that already exists.
- Do not leave important backend behavior protected only by manual validation when deterministic pytest coverage is practical.
