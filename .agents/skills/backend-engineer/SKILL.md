---
name: backend-engineer
description: Implement SimBoard backend APIs, schemas, models, ingestion logic, and service behavior in the existing FastAPI, SQLAlchemy, Alembic, and uv-based backend.
---

# Backend Engineer

## Overview

Implement or modify SimBoard backend behavior with minimal changes that fit the existing FastAPI, SQLAlchemy, Alembic, and `uv` workflows.

## Use When

- Adding or changing backend endpoints, schemas, models, or feature logic
- Updating ingestion, auth, token, or persistence behavior
- Making backend changes that may require tests, migrations, or seed updates

## Workflow

1. Inspect the touched feature, neighboring schemas/models, and existing tests before editing.
2. Reuse current patterns in `backend/app/features/*`, `backend/app/common/*`, and `backend/app/core/*`.
3. Keep API contracts camelCase unless the existing endpoint is intentionally different.
4. Update tests, migrations, router registration, model imports, or seed data when the change requires them.
5. Validate with repo commands such as `make backend-test`.

## Repo Rules

- Keep feature logic inside `backend/app/features/<feature>/`.
- Register top-level routers in `backend/app/main.py`.
- If a model must be imported for metadata discovery, update `backend/app/models/__init__.py`.
- Request models normally inherit from `CamelInBaseModel`; response models normally inherit from `CamelOutBaseModel`.
- Match existing dependency patterns such as `Depends(get_database_session)` and `Depends(current_active_user)`.
- Prefer the existing sync `Session` plus `transaction(db)` pattern unless the touched code already uses the async path.
- When schema or model changes affect seeded data, check `backend/app/scripts/db/*`.
- Use repo workflows for migrations and environment management: `make backend-migrate`, `make backend-upgrade`, and `uv`.

## Guardrails

- Do not add new dependencies, async rewrites, or background systems without a concrete repo need.
- Do not change auth, token, or env-loading behavior casually; these need focused tests.
- Do not scatter `db.commit()` calls when the transactional helper is the established pattern.
- Do not ship persistence or contract changes without checking tests, migrations, and compatibility.
