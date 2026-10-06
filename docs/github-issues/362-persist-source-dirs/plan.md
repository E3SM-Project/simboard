# Issue #362 — Persist performance source directories

## Problem

Map ingested cases and executions to their original performance staging and archive directories so operators can locate source data. Display the mappings on Case Details and Execution Details.

## Scope

### Phase 1 — Storage and persistence

- Add minimal case- and execution-associated directory mappings with staging/archive kind and observed original path.
- Retain multiple paths; full archive paths distinguish snapshot locations without separate snapshot metadata.
- Enforce database uniqueness per owner, kind, and path, with concurrency-safe idempotent persistence.
- Keep mappings separate from simulation artifacts and use the associated case for machine context.

Affected files: `backend/app/features/catalog/{models,enums,schemas}.py`, a small persistence helper, and a new Alembic migration under `backend/migrations/versions/`.

### Phase 2 — Normal ingestion and discovery

- Pass original case and execution directory paths explicitly from scanners.
- Resolve cases by case name, machine, and HPC username; resolve executions by the associated case and execution ID.
- Obtain identifiers from parsed metadata or reliable existing ingestion provenance, not directory basenames or execution IDs alone.
- Persist mappings for new and duplicate executions, including visited directories whose uploads are skipped.
- Collect paths before execution-level duplicate filtering. Use a lightweight metadata submission path when no upload occurs.
- Report ambiguous or unresolved mappings without guessing or creating placeholder records.
- Persist required mappings before completing affected archive checkpoints. Rejected-only discoveries without an associated ingested record do not require mappings and must not block checkpoints indefinitely.
- Preserve normal snapshot-level checkpoint pruning: directories not visited produce no new mappings.

Affected files: `backend/app/features/ingestion/{schemas,api,ingest}.py` and relevant discovery, client, core, runner, and workflow modules under `backend/app/scripts/ingestion/`. Any new endpoint module follows repository routing instructions.

### Phase 3 — Detail APIs

- Return case-directory mappings through the case-detail API and execution-directory mappings through the execution-detail API.
- Use consistent response fields and appropriate eager loading.
- Restrict scanner metadata writes to the existing trusted ingestion roles; preserve detail-read authorization and legacy requests without path metadata.

Affected files: `backend/app/features/catalog/{schemas,api}.py` and corresponding tests.

### Phase 4 — UI display

- Add a **Performance Source Directories** section to Case Details and Execution Details.
- Label each path **Staging** or **Archive**, support multiple paths, and provide copy actions.
- Omit the section when mappings are absent and keep it separate from simulation output/archive artifacts.
- Do not imply that stored paths still exist.

Affected files: case/execution API types and detail components under `frontend/src/features/`; identify exact files before editing. Reuse existing shared components and preserve feature boundaries.

### Phase 5 — Documentation and final validation

- Document observed-path semantics and collection during normal ingestion.
- Explain that previously checkpointed snapshots remain skipped; historical backfill belongs to issue #360.
- Complete the checks listed below and report their results.

Affected files: `docs/architecture/metadata-ingestion.md`, `backend/app/scripts/README.md`, and relevant backend/frontend tests.

## Constraints and non-goals

- Preserve case identity, execution deduplication, and normal checkpoint skipping.
- Keep performance source mappings separate from `CASEROOT`, `RUNDIR`, `DOUT_S_ROOT`, and simulation artifacts.
- Never fabricate original paths from temporary extraction directories or upload filenames.
- Missing path metadata neither inserts mappings nor deletes existing ones.
- Preserve legacy requests and dry-run non-mutation.
- No historical backfill or checkpoint-bypass feature; those belong to #360.
- No generalized provenance framework, dedicated observation-history tracking, or new dependencies.

Non-blocking assumptions: retain historical staging paths; full archive paths sufficiently distinguish snapshots; unvisited directories remain unchanged. Separate source/snapshot fields and observation timestamps from the original issue are intentionally omitted in favor of the agreed minimal directory-mapping scope.

Risks: incorrect attribution to same-named cases, insufficient identifiers in skipped-upload flows, observations lost through duplicate filtering, checkpoint completion before persistence succeeds, and UI confusion with simulation artifacts. Verify available identifiers during Phase 2; surface unresolved records rather than weakening identity matching.

## Acceptance criteria

- Case Details displays original case directories and Execution Details displays original execution directories, with staging/archive labels and copy actions.
- Both pages omit the section without errors when mappings are absent.
- Multiple locations remain retrievable; repeated and concurrent submissions create no duplicate mappings.
- Duplicate-only ingestion and skipped uploads persist mappings for directories actually visited.
- Same-named cases belonging to different users or machines receive only their own mappings.
- Missing or unresolved data produces no fabricated mappings or placeholder records.
- Failed required mapping persistence prevents affected snapshots from being checkpointed.
- Rejected-only discoveries without ingested records do not create phantom records or indefinitely block checkpoints.
- Previously checkpointed snapshots remain skipped and unchanged.
- Case identity, execution deduplication, authorization, legacy requests, and dry-run behavior remain unchanged.

## Validation

- Phase 1: test ownership, cascade behavior, database uniqueness, concurrent idempotent persistence, and migration upgrade/downgrade on disposable PostgreSQL.
- Phases 2–3: extend ingestion/catalog tests for identity matching, multiple paths, repeated submissions, duplicate-only ingestion, skipped uploads, missing paths, unresolved mappings, authorization, and detail responses.
- Phase 2: extend scanner/client/workflow tests for persistence ordering, failures, rejected-only discoveries, preserved checkpoint pruning, legacy payloads, and dry-run non-mutation.
- Phase 4: use the existing frontend test setup for rendering and copy actions where available. Manually check both pages with staging, archive, multiple-path, and no-path cases; long paths must remain readable.
- Run `make backend-test` after backend changes, `make frontend-lint` after frontend changes, and `make pre-commit-run` from the repository root for final checks. Run the frontend build using the repository's existing build command.
- Report unavailable checks and their blockers rather than claiming completion.

This document is a phased implementation plan, not a record of completed implementation or validation.
