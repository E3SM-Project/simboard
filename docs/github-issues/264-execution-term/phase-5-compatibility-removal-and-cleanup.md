# Phase 5 Plan: Compatibility Removal and Cleanup

## Task

Remove expired simulation-entity compatibility paths and finish the repository
terminology cleanup after canonical execution contracts have been deployed and
consumers have migrated.

## Scope

### In scope

- Deprecated `/api/v1/simulations` API routes
- Deprecated response-field and assistant citation aliases
- Legacy backend and frontend compatibility adapters
- Remaining entity-oriented simulation/run symbols, package paths, docs, tests,
  fixtures, and log messages
- Final API, frontend navigation, and terminology regression coverage

### Out of scope

- Removing valid scientific simulation metadata
- Renaming CIME `case.run`, runner operations, scheduler jobs, or run date fields
- Removing useful browser redirects unless product policy explicitly requires it
- Unrelated backend or frontend architecture changes

## Preconditions

- Canonical `/api/v1/executions` endpoints have been deployed and monitored.
- First-party frontend and automated ingestion clients use canonical contracts.
- Known external consumers have completed migration or accepted the breaking
  change.
- Phase 4 database migration is complete in supported environments.
- Removal is scheduled as an explicit breaking release when required by project
  policy.

## Approach

1. Remove deprecated backend contracts.
   - Remove `/api/v1/simulations` compatibility routes and their legacy response
     schemas.
   - Remove deprecated `simulations`, `totalSimulations`, and similar entity
     aliases from shared responses.
   - Remove legacy `simulation.*` assistant citation-path acceptance after
     confirming it is not needed for stored or provider-generated content.
   - Remove compatibility aliases for old Python class and function names.

2. Remove obsolete frontend compatibility code.
   - Remove legacy API adapters, old query keys, and dual-shape response parsing.
   - Keep `/simulations` browser redirects by default because they preserve
     bookmarks at low maintenance cost; remove them only through an explicit
     product decision.
   - Confirm all generated navigation uses `/executions`.

3. Clean feature and module naming.
   - Rename remaining backend or frontend package paths whose names still imply
     the child entity is a simulation.
   - Prefer a neutral catalog package when a module owns both cases and
     executions; do not split features solely for naming purity.
   - Update imports mechanically without changing feature boundaries or data
     flow.

4. Audit terminology by meaning.
   - Search backend, frontend, tests, fixtures, scripts, and current docs for
     entity-level `simulation`, `simulations`, `run`, and `runs`.
   - Classify each remaining match against the Phase 1 terminology contract.
   - Keep legitimate scientific, temporal, command, runner, and scheduler uses.
   - Do not rewrite historical migrations or historical issue notes merely to
     make repository-wide search results empty.

5. Finalize current documentation.
   - Remove deprecation guidance from canonical API and developer docs.
   - Describe only `Case -> Execution` in current architecture and user docs.
   - Record any permanently retained browser redirect as compatibility behavior,
     not as a second canonical term.

## Tests

- Update API tests to confirm canonical execution endpoints and response fields
  remain complete after compatibility removal.
- Add negative tests confirming removed simulation API routes return the
  intended not-found response.
- Update assistant tests to accept only canonical execution citation paths.
- Verify frontend navigation, compare, upload results, and details pages create
  only `/executions` URLs.
- Perform reviewed terminology searches across current source and docs.
- Run:
  - `make backend-test`
  - `make frontend-lint`
  - `pnpm --dir frontend run type-check`
  - `make pre-commit-run`

## Risk

- Risk score: 6
- Main failure modes:
  - An untracked external client still depends on deprecated API contracts.
  - Provider-generated assistant citations still use legacy roots.
  - Package moves create broken imports or frontend boundary violations.
  - Cleanup incorrectly renames legitimate CIME or scientific terms.
  - Removing browser redirects breaks bookmarks and historical links.

## Open Questions

None. Compatibility removal must not begin until the listed preconditions are
verified.
