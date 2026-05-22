# Phase 3 Plan: Aggregate Case Diagnostics Into Existing Responses

## Task

Make existing simulation detail, simulation list, and assistant summary paths expose case-scoped diagnostic links without changing frontend contracts.

## Scope

### In scope

- Response aggregation in simulation API
- Relationship loading updates needed to read `Case.links`
- Assistant snapshot and summary loading updates
- Backend tests proving payload shape stays compatible

### Out of scope

- Provenance scanner script
- New frontend UI or TypeScript contract changes
- Changing `CaseOut`

## Approach

1. Add merged-link helper in simulation feature.
   - Merge `Simulation.links` with `Simulation.case.links`.
   - Deduplicate by `(kind, url)`.
   - Prefer simulation-owned row when same `(kind, url)` exists on both simulation and case.

2. Use merged links in simulation responses.
   - Keep `SimulationOut.links` shape unchanged.
   - Keep computed `grouped_links` behavior unchanged.
   - Ensure merged list is passed into `SimulationOut` generation for both simulation list and simulation detail endpoints.

3. Load case links everywhere needed.
   - Update list and detail query options in `backend/app/features/simulation/api.py` to eager-load `Case.links` alongside `Simulation.links`.
   - Avoid introducing extra lazy-load queries in hot paths.

4. Update assistant paths.
   - Update `backend/app/features/assistant/api.py` query options so assistant summary loads case links.
   - Update `backend/app/features/assistant/snapshot.py` so snapshot links include merged case-owned diagnostics, not only direct simulation links.

5. Preserve current frontend behavior.
   - Do not change frontend API shapes or field names.
   - Do not add case-scoped links to `CaseOut` in this phase.

## Tests

- Update simulation API tests to verify:
  - simulation detail includes case-owned diagnostic links
  - simulation list includes case-owned diagnostic links
  - duplicate `(kind, url)` across case and simulation appears once
  - simulation-owned link wins on duplicate URL
- Update assistant tests to verify case-scoped diagnostic links are visible to summary generation and citations.
- Run:
  - `make backend-test`

## Risk

- Risk score: 5
- Main failure modes:
  - Duplicate links leak into API payload.
  - Assistant path and simulation path expose different link sets.

## Open Questions

None.
