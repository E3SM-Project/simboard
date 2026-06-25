# Phase 3 Plan: Aggregate Case Diagnostics Into Existing Responses

## Task

Make simulation detail, simulation list, assistant summary, and case details paths expose case-scoped diagnostic links, including case-level diagnostics on case details page.

## Scope

### In scope

- Response aggregation in simulation API
- Case detail API and UI updates needed to show case-owned diagnostic links
- Relationship loading updates needed to read `Case.links`
- Assistant snapshot and summary loading updates
- Backend and frontend tests proving payload shape stays compatible where required

### Out of scope

- Provenance scanner script
- Unrelated frontend UI or TypeScript contract changes

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

5. Update case details path.
   - Ensure case detail response exposes case-owned diagnostic links needed by case details page.
   - Update case details page to render case-level diagnostic links in diagnostics section.
   - Preserve existing simulation-page contracts while adding case-page support.

6. Preserve current frontend behavior where unchanged.
   - Do not change frontend API shapes or field names.
   - Keep simulation response contracts stable while making minimal changes required for case details.

## Tests

- Update simulation API tests to verify:
  - simulation detail includes case-owned diagnostic links
  - simulation list includes case-owned diagnostic links
  - duplicate `(kind, url)` across case and simulation appears once
  - simulation-owned link wins on duplicate URL
- Update assistant tests to verify case-scoped diagnostic links are visible to summary generation and citations.
- Update case detail API and frontend tests to verify case-level diagnostic links render on case details page.
- Run:
  - `make backend-test`
  - `make frontend-lint`

## Risk

- Risk score: 5
- Main failure modes:
  - Duplicate links leak into API payload.
  - Assistant path and simulation path expose different link sets.

## Open Questions

None.
