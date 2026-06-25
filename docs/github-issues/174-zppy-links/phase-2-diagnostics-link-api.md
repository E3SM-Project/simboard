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
- Broad link-model redesign beyond ownership metadata needed by simulation editing

## Approach

1. Add diagnostics-link request schemas.
   - Add `DiagnosticsLinkRequest` with required `case_name`, `machine`, `hpc_username`, and `diagnostics`.
   - Add `DiagnosticsLinkItem` with required `name`, `url`, and `kind="diagnostic"`.

2. Add new internal endpoint.
   - Route: `POST /api/v1/diagnostics/link`
   - Success response: `204 No Content`
   - Endpoint lives in `backend/app/features/simulation/api.py`, but uses a dedicated `diagnostics_router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])` rather than the existing `/simulations` router.
   - Register `diagnostics_router` in `backend/app/main.py` with the same `API_BASE` prefix as other feature routers so the final path is exactly `/api/v1/diagnostics/link`.

3. Enforce auth and access policy.
   - Require authenticated user from existing `current_active_user` dependency.
   - Allow only `ADMIN` and `SERVICE_ACCOUNT`.
   - Return `403` for authenticated non-admin, non-service-account users.

4. Resolve case match from existing data.
   - Canonicalize request machine name through existing machine resolver in `backend/app/features/machine/utils.py`.
   - Accept known aliases and case-insensitive inputs such as `pm`, `pm-cpu`, `pm-gpu`, and `Perlmutter`.
   - Resolve target machine first, then match `Case.name == case_name`, `Case.machine_id == resolved_machine.id`, and `Case.hpc_username == hpc_username`.
   - Return `404` when machine cannot be resolved or when no case matches the full `(case_name, machine, hpc_username)` identity.
   - Do not model `409` ambiguity in normal contract. Current `Case` uniqueness is enforced on `(name, machine_id, hpc_username)`.

5. Persist idempotent links.
   - Create case-owned `ExternalLink` rows with `kind="diagnostic"`.
   - Treat the Phase 1 partial unique index on `(case_id, kind, url)` as the source of truth for idempotency.
   - Use conflict-safe write logic so repeated or concurrent requests for the same `(case_id, kind, url)` do not create duplicate rows.
   - If same URL already exists for case, update label from diagnostics item `name` instead of inserting duplicate.

6. Preserve simulation-owned PATCH semantics.
   - Keep simulation detail responses merged so consumers can still see inherited case links.
   - Add explicit link ownership metadata to response links so simulation editors can treat case-owned links as read-only.
   - Keep `PATCH /api/v1/simulations/{id}` replacing only simulation-owned links, never case-owned links.

## Tests

- Add API coverage for:
  - machine alias and case-insensitive inputs resolving through diagnostics link endpoint
  - successful create
  - duplicate request remains idempotent
  - concurrent duplicate request remains idempotent
  - `401` unauthenticated
  - `403` authenticated but wrong role
  - `404` unknown machine
  - `404` no matching case
  - `422` invalid payload
  - merged simulation-link responses carrying ownership metadata so frontend editors can exclude inherited case links from PATCH payloads
- Reuse existing service-account token auth patterns already used by ingestion tests.
- Run:
  - `make backend-test`
  - `make frontend-lint`

## Risk

- Risk score: 4
- Main failure modes:
  - Canonical machine resolution points at wrong machine.
  - Idempotency logic inserts duplicate rows under repeated requests.
  - Ownership metadata is not consumed consistently by frontend editors.

## Open Questions

None.
