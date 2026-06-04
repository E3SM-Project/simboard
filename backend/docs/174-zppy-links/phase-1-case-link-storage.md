# Phase 1 Plan: Case-Scoped Link Storage

## Task

Extend backend data model so an external link can belong to either a simulation or a case, without changing existing simulation-scoped link behavior.

## Scope

### In scope

- `ExternalLink` ownership model changes in `backend/app/features/simulation/models.py`
- Alembic migration in `backend/migrations/versions`
- ORM relationships for `Case.links`
- Model and schema test updates needed for new ownership rules

### Out of scope

- New diagnostics-link API endpoint
- Provenance scanner script
- Simulation response aggregation logic
- Frontend changes

## Approach

1. Update `ExternalLink` ownership in `backend/app/features/simulation/models.py`.
   - Add nullable `case_id` foreign key to `cases.id`.
   - Make `simulation_id` nullable.
   - Add `Case.links` relationship and matching `ExternalLink.case` relationship.
   - Keep existing `Simulation.links` relationship intact.

2. Add database invariants in Alembic migration.
   - Backfill nothing; existing rows remain simulation-owned.
   - Add check constraint enforcing exactly one owner per row: `case_id` xor `simulation_id`.
   - Add partial unique index for case-owned diagnostics on `(case_id, kind, url)` where `case_id IS NOT NULL`.
   - Leave simulation-owned link uniqueness unchanged in this phase.
   - Preserve cascade semantics for both ownership paths.

3. Preserve current write behavior.
   - Manual simulation create flow and archive-ingestion flow continue writing only simulation-owned links.
   - No API contract changes in this phase.

## Tests

- Update model and schema coverage to validate:
  - simulation-owned external link is valid
  - case-owned external link is valid
  - ownerless external link is invalid
  - dual-owned external link is invalid
  - duplicate case-owned diagnostic link violates the new DB uniqueness invariant
- Run:
  - `make backend-test`

## Risk

- Risk score: 3
- Main failure modes:
  - Migration breaks existing `external_links` rows or ORM loads.
  - Owner constraint behaves differently across SQLite test DB and PostgreSQL.

## Open Questions

None.
