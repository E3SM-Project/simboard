# Phase 1 Plan: Shared Contracts and Configuration

## Task

Create the stable low-level module used by later extractions. Move shared
types, configuration parsing, logging primitives, fingerprints, and pure state
helpers without changing either runner's orchestration.

## Scope

### In scope

- New `backend/app/scripts/ingestion/archive_ingestor_core.py`
- Runtime dataclasses, typed dictionaries, and shared exceptions
- Environment parsing and `IngestorConfig` construction
- Stable non-layout configuration constants
- Structured logging field order and value rendering
- Fingerprint and pure ingestion-state helpers
- Immutable discovery-result precedence and deduplication helpers
- NERSC and HPC imports for moved definitions

### Out of scope

- Archive path filtering or traversal
- Candidate selection
- HTTP requests or retries
- Moving `_run_ingestor`, request implementations, or module guards
- Changing environment names, defaults, validation, state version, or logs

## Approach

1. Add `archive_ingestor_core.py` as the dependency root.
   - Move shared dataclasses, typed dictionaries, and exceptions.
   - Move configuration construction and parsing helpers.
   - Move structured logging helpers and event-field ordering.
   - Move fingerprint, processed-ID extraction, fresh-state creation, and
     successful-case state updates when they have no runner dependency.
   - Move immutable discovery-result precedence and deduplication because both
     discovery settlement and client persistence consume that policy.

2. Preserve contracts byte-for-byte where practical.
   - Keep environment parsing, defaults, validation messages, state shape,
     timestamps, event names, and field ordering unchanged.
   - Keep `STATE_VERSION` semantics unchanged.

3. Update both runner imports.
   - Import shared definitions from `archive_ingestor_core.py`.
   - Do not import shared definitions through `nersc_archive_ingestor.py`.
   - Keep runner `main()` functions and module guards in place.

4. Update tests with minimal churn.
   - Point direct unit imports to `archive_ingestor_core.py`.
   - Patch logger and time dependencies where their runtime lookup now lives.
   - Retain runner-level assertions in existing runner test files.

## Tests

- Configuration accepts and rejects the same values with the same messages.
- State and fingerprint helpers return identical shapes and values.
- Structured log values and event field ordering remain unchanged.
- Both runner `main()` functions still report configuration failures and
  completion events correctly.
- Run targeted runner tests, `make backend-test`, and `make pre-commit-run`.

## Risk

- Risk score: 4
- Main failure modes:
  - Moved logger or clock lookup breaks monkeypatching.
  - Constants move into a module that later causes circular imports.
  - Environment defaults or validation messages drift during extraction.

## Open Questions

None.
