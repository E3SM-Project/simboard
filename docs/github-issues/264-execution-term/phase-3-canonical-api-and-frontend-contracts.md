# Phase 3 Plan: Canonical API and Frontend Contracts

## Task

Add execution-oriented API contracts and migrate the frontend to them while
retaining temporary compatibility for existing `/simulations` clients and
saved frontend URLs.

## Scope

### In scope

- Canonical `/api/v1/executions` endpoints and OpenAPI tags
- Execution-oriented API response fields and assistant paths
- Deprecated `/api/v1/simulations` compatibility routes and legacy payloads
- Frontend `Execution*` types, API functions, hooks, query keys, state, routes,
  and component symbols
- Browser redirects from `/simulations` to `/executions`
- API and frontend compatibility tests

### Out of scope

- Database table or foreign-key column renames
- Removing deprecated API routes or fields
- Removing browser redirects for saved links
- Unrelated API versioning or frontend feature restructuring

## Approach

1. Add the canonical execution router.
   - Expose list, filter-options, create, detail, and update behavior under
     `/api/v1/executions`.
   - Use `Executions` as the OpenAPI tag and execution-oriented operation names,
     descriptions, parameters, and error messages.
   - Share query and mutation services with compatibility routes so behavior
     cannot diverge.

2. Add canonical response contracts.
   - Use `ExecutionCreate`, `ExecutionUpdate`, `ExecutionOut`,
     `ExecutionListItemOut`, `ExecutionPageOut`, and related schemas.
   - Expose case children as `executions` and catalog totals as
     `totalExecutions`.
   - Expose created ingestion children as `executions`.
   - Move assistant entity endpoints and citation roots to execution
     terminology where those values are part of the public contract.

3. Preserve legacy API behavior during the deprecation window.
   - Keep `/api/v1/simulations` routes as deprecated wrappers over the same
     execution services.
   - Use explicit legacy response schemas for old routes when field names
     differ; do not make canonical schemas permanently emit both vocabularies.
   - For shared endpoints such as ingestion or overview, provide temporary
     deprecated aliases only where a route-specific legacy schema is not
     practical.
   - Mark deprecated operations and fields in OpenAPI and response metadata.

4. Migrate the frontend API boundary.
   - Update `frontend/src/types/simulation.ts` or replace it with an
     execution-oriented type module.
   - Update `frontend/src/api/catalog.ts`, catalog hooks, query keys, and cache
     invalidation to consume `/executions` and canonical field names.
   - Rename entity variables, props, selection state, compare state, and upload
     result types from simulation/run terminology to execution terminology.
   - Preserve scientific field names such as `simulationType` and
     `simulationStartDate`.

5. Migrate frontend routes safely.
   - Add `/executions` and `/executions/:id` as canonical routes.
   - Redirect `/simulations` and `/simulations/:id` to their canonical
     equivalents while preserving IDs, query parameters, and navigation state
     where supported.
   - Update generated links, breadcrumbs, compare links, upload-result links,
     and back-navigation labels.

6. Align assistant and comparison contracts.
   - Rename execution entity snapshot and citation paths without changing
     scientific metadata field names.
   - Accept legacy `simulation.*` citation paths during the compatibility
     window if they can appear in stored or provider-generated content.
   - Ensure cross-case and within-case comparison state uses execution IDs and
     execution-oriented labels consistently.

## Tests

- Add backend API coverage for canonical execution list, filters, create,
  detail, update, case children, overview totals, ingestion results, and
  assistant responses.
- Add parity tests proving deprecated simulation routes delegate to the same
  behavior and retain their legacy payload shape.
- Add OpenAPI assertions that canonical operations use execution terminology
  and compatibility operations are marked deprecated.
- Add or update frontend coverage for:
  - execution routes
  - old-route redirects
  - catalog fetching and cache keys
  - compare selection and navigation
  - upload-result navigation
  - assistant citation compatibility
- Run:
  - `make backend-test`
  - `make frontend-lint`
  - `pnpm --dir frontend run type-check`
  - `make pre-commit-run`

## Risk

- Risk score: 7
- Main failure modes:
  - Canonical and compatibility endpoints return different data or permissions.
  - Shared responses expose duplicate or contradictory fields.
  - Saved links lose query parameters or selected execution state.
  - Frontend cache keys mix old and new resources and show stale data.
  - Assistant citations break when legacy paths are encountered.

## Open Questions

None. Deprecated contract removal occurs only through the explicit Phase 5
change, after the project-selected compatibility window.
