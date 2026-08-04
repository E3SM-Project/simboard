# Phase 5 Plan: Runner Integration and HPC Cleanup

## Task

Finish module integration, extract remaining shared workflow helpers, leave the
NERSC and HPC files as transport-specific entrypoints, and remove all HPC
imports from the NERSC runner module.

## Scope

### In scope

- New `backend/app/scripts/ingestion/archive_workflow.py`
- Shared dry-run, candidate-ingestion, startup, and completion-summary helpers
- Thin `nersc_archive_ingestor.py`
- Direct shared-module imports in `hpc_upload_archive_ingestor.py`
- Final import, entrypoint, documentation-reference, and regression cleanup

### Out of scope

- Replacing both `_run_ingestor` functions with one generic runner
- Changing the order of state and checkpoint reads
- Standardizing currently different exception classification between runners
- Changing NERSC path requests or HPC multipart requests
- New CLI or configuration surface

## Approach

1. Add `archive_workflow.py` for shared run-completion behavior.
   - Move dry-run candidate logging and summaries.
   - Move per-candidate ingestion handling and completion summaries.
   - Keep dependencies explicit through arguments; do not import entrypoints.

2. Thin the NERSC entrypoint.
   - Retain `main()`, `_run_ingestor`, path-specific endpoint/request selection,
     and module guard.
   - Import configuration, layout, discovery, client, and workflow behavior
     from owning modules.
   - Preserve NERSC handling of unsupported archive layouts as configuration
     errors.

3. Decouple the HPC entrypoint.
   - Replace every import from `nersc_archive_ingestor.py` with an import from
     the owning shared module.
   - Retain case archive creation, multipart encoding, upload request,
     `_run_ingestor`, `main()`, and module guard.
   - Preserve current HPC checkpoint/state ordering and generic scan-failure
     classification.

4. Remove transitional exports and imports.
   - Delete unused imports and duplicate implementations.
   - Do not keep broad private-name re-export shims solely for old tests.
   - Update test imports and monkeypatch targets to actual owners.

5. Verify entrypoints and documentation references.
   - Keep both documented `python -m app.scripts.ingestion...` commands.
   - Update module docstrings or `backend/app/scripts/README.md` only if they
     incorrectly describe code ownership after extraction.
   - Leave operational behavior documentation unchanged.

## Tests

- NERSC and HPC runner tests pass without importing shared behavior through the
  NERSC module.
- Both module guards exit through `SystemExit` with current codes.
- Dry-run, missing-root, missing-token, state failure, scan failure,
  persistence failure, successful ingestion, and checkpoint paths remain
  covered for both runners.
- Structured startup, scan, candidate, and completion logs retain current
  event names and field order.
- Add a simple import-boundary assertion or reviewed `rg` check confirming
  `hpc_upload_archive_ingestor.py` does not import
  `nersc_archive_ingestor.py`.
- Run:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_nersc_archive_ingestor.py \
  tests/features/ingestion/test_hpc_upload_archive_ingestor.py
```

```bash
make backend-test
make pre-commit-run
```

## Risk

- Risk score: 5
- Main failure modes:
  - Final imports create a cycle hidden during earlier phases.
  - Shared workflow changes runner-specific event order or exception handling.
  - Entry-point imports work in tests but fail under `python -m`.
  - Cleanup removes an internal name still used by the other runner.

## Open Questions

None.
