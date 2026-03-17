---
name: backend-engineer
description: Implement SimBoard backend APIs, schemas, models, ingestion logic, and service behavior in the existing FastAPI, SQLAlchemy, Alembic, and uv-based backend.
---

# Backend Engineer

## Purpose

Implement or modify SimBoard backend behavior with minimal, maintainable changes that fit the current FastAPI and SQLAlchemy architecture.

## When To Use

- Adding or changing REST endpoints
- Updating Pydantic schemas, feature logic, or auth/token behavior
- Modifying ORM models or ingestion/parsing logic
- Creating database migrations or changing persistence behavior

## Inputs Expected

- The requested backend behavior
- Affected feature area such as simulation, machine, ingestion, or user
- Expected request/response shape
- Auth/authorization rules
- Database or migration impact

## Outputs Required

- Backend code changes in `backend/app/**` and migrations if needed
- Updated tests or identified test gaps
- Registration updates when new routers or models are introduced
- Validation notes for commands that were run

## Repo-Specific Conventions

- Keep domain code inside `backend/app/features/<feature>/`.
- Put shared helpers in `backend/app/common/` or `backend/app/core/` only when they are truly cross-feature.
- Register top-level routers in `backend/app/main.py`.
- If a new model module must be imported for metadata discovery, update `backend/app/models/__init__.py`.
- Request models should normally inherit from `CamelInBaseModel`; response models should normally inherit from `CamelOutBaseModel`.
- Use the existing sync SQLAlchemy session pattern with `Session` and `transaction(db)` unless the touched code already uses the async path.
- Match existing FastAPI dependency injection patterns such as `Depends(get_database_session)` and `Depends(current_active_user)`.
- Respect current role checks in `app.features.user.models.UserRole` and related auth helpers.
- Use Alembic through the repo workflow: `make backend-migrate m='message'` and `make backend-upgrade`.
- Use `uv` and repo make targets, not `pip` or ad hoc virtualenv commands.

## Constraints / Anti-Patterns

- Do not return snake_case payloads to the frontend unless the existing endpoint already does so intentionally.
- Do not scatter raw `db.commit()` calls when the existing transactional helper is the better fit.
- Do not add async endpoints, background workers, or new dependencies without a concrete need.
- Do not change env loading, OAuth flow, or token semantics casually; these changes need tests and usually docs.
- Do not bypass feature boundaries by placing feature logic in `main.py` or unrelated modules.
- Do not ship schema or model changes without considering migrations, seed scripts, and API compatibility.

## Example Task

Add a backend endpoint that exposes a filtered list of simulations for the browse UI by updating `backend/app/features/simulation/api.py`, any needed schemas in `backend/app/features/simulation/schemas.py`, relevant model/query logic, and tests under `backend/tests/features/simulation/`.
