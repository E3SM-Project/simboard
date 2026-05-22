# Phase 2 Plan: Internal Diagnostics Link API

## Task

Add backend-only endpoint that resolves one case by `(case_name, machine, hpc_username)` and creates idempotent case-scoped diagnostic links.

## Scope

### In scope

- Diagnostics-link request schemas in `backend/app/features/simulation/schemas.py`
- Internal endpoint in `backend/app/features/simulation/api.py`
- Match resolver and authorization logic
- API test coverage for endpoint behavior

### Out of scope

- Provenance scanner script
- Frontend changes
- Aggregating case-scoped links into simulation responses

## Approach

1. Add diagnostics-link request schemas.
   - Add `DiagnosticsLinkRequest` with required `case_name`, `machine`, `hpc_username`, and `diagnostics`.
   - Add `DiagnosticsLinkItem` with required `name`, `url`, and `kind="diagnostic"`.

2. Add new internal endpoint.
   - Route: `POST /api/v1/diagnostics/link`
   - Success response: `204 No Content`
   - Endpoint lives in existing simulation feature router module.

3. Enforce auth and access policy.
   - Require authenticated user from existing `current_active_user` dependency.
   - Allow only `ADMIN` and `SERVICE_ACCOUNT`.
   - Return `403` for authenticated non-admin, non-service-account users.

4. Resolve case match from existing data.
   - Match `Case.name == case_name`.
   - Join through `Simulation` and `Machine`.
   - Require one joined simulation with matching `Machine.name == machine`.
   - Require same joined simulation to have matching `Simulation.hpc_username == hpc_username`.
   - Return `404` when no case matches.
   - Return `409` when multiple cases match.

5. Persist idempotent links.
   - Create case-owned `ExternalLink` rows with `kind="diagnostic"`.
   - Upsert by `(case_id, kind, url)` in application logic.
   - If same URL already exists for case, update label from diagnostics item `name` instead of inserting duplicate.

## Tests

- Add API coverage for:
  - successful create
  - duplicate request remains idempotent
  - `401` unauthenticated
  - `403` authenticated but wrong role
  - `404` no matching case
  - `409` ambiguous match
  - `422` invalid payload
- Reuse existing service-account token auth patterns already used by ingestion tests.
- Run:
  - `make backend-test`

## Risk

- Risk score: 4
- Main failure modes:
  - Resolver query matches duplicate cases unexpectedly.
  - Idempotency logic inserts duplicate rows under repeated requests.

## Open Questions

None.
