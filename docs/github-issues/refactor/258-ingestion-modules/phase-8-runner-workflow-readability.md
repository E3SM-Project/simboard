# Phase 8 Plan: Runner Workflow Readability

## Task

Shorten and clarify both `_run_ingestor()` functions with named workflow-phase
helpers. Keep each runner's distinct operation order, transport, error mapping,
events, and exit codes explicit.

## Scope

### In scope

- `backend/app/scripts/ingestion/archive_workflow.py`
- `backend/app/scripts/ingestion/nersc_archive_ingestor.py`
- `backend/app/scripts/ingestion/hpc_upload_archive_ingestor.py`
- Shared discovery-summary field construction
- Workflow-owned test extraction and both runner regression suites

### Out of scope

- One configurable generic `_run_ingestor()` implementation
- Base classes, dependency containers, or a workflow engine
- Changing NERSC state-before-checkpoint order
- Changing HPC checkpoint-before-state order
- Standardizing different unsupported-layout error classification
- HTTP request internals; Phase 9 handles them

## Approach

1. Move workflow-owned tests to a focused module.
   - Create `backend/tests/features/ingestion/test_archive_workflow.py`.
   - Move startup, dry-run, ingestion-loop, and summary tests without changing
     their assertions.

2. Centralize discovery summary construction.
   - Add one helper that maps `DiscoveryStats` to the stable event fields.
   - Reuse it for `scan_completed`, dry-run completion, and ingest completion.
   - Preserve `EVENT_FIELD_ORDER` and every current event field.

3. Extract narrow workflow phases, not a generic runner.
   - Add named helpers for precondition validation, scan-completion logging,
     discovery-result persistence, candidate ingestion, and archive-checkpoint
     finalization where they remove repeated blocks.
   - Accept explicit typed arguments and return simple values; avoid option
     dictionaries, mode switches, callback registries, and nested functions.
   - Keep endpoint choice and default transport in each runner.

4. Rewrite each runner as visible ordered phases.
   - NERSC order remains: validate, fetch state, fetch archive checkpoints,
     scan, dry-run or persist/ingest, settle checkpoints.
   - HPC order remains: validate, fetch archive checkpoints, fetch state, scan,
     dry-run or persist/upload, settle checkpoints.
   - Keep NERSC-specific `UnsupportedArchiveLayoutError` handling and HPC's
     generic scan-failure handling in their entrypoint modules.

5. Remove complexity suppressions when the runner bodies pass naturally.
   - Keep `main()` and module guards local and unchanged.
   - Confirm shared workflow never imports either runner.

## Tests

- Assert both runners' exact state/checkpoint request order.
- Retain dry-run, missing-root, missing-token, state failure, checkpoint failure,
  scan failure, persistence failure, partial ingestion failure, and success
  coverage.
- Assert exact startup, scan, candidate, completion, and run-finished events.
- Assert module guards and both documented module entrypoints.
- Run:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_archive_workflow.py \
  tests/features/ingestion/test_nersc_archive_ingestor.py \
  tests/features/ingestion/test_hpc_upload_archive_ingestor.py
```

```bash
uv run --project backend mypy backend/app/scripts/ingestion
uv run --project backend ruff check backend/app/scripts/ingestion
make backend-test
make pre-commit-run
```

## Risk

- Risk score: 5
- Main failure modes:
  - Shared helpers accidentally reorder remote reads or persistence writes.
  - A helper collapses runner-specific exception handling into one behavior.
  - Early returns change exit codes or suppress final events.
  - Injected request functions or logger callbacks resolve in a different
    module, breaking tests or scheduled behavior.

## Open Questions

None.
