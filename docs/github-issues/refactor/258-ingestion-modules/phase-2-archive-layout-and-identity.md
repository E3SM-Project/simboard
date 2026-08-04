# Phase 2 Plan: Archive Layout and Identity

## Task

Extract archive layout, range, filtering, path normalization, case identity,
and snapshot enumeration into one focused module. Keep traversal and candidate
selection in their current location until Phase 3.

## Scope

### In scope

- New `backend/app/scripts/ingestion/archive_layout.py`
- Archive range parsing support needed by layout selection
- Root-layout validation and directory pruning
- Snapshot and status-bucket recognition
- Staging and archive case-identity normalization
- Snapshot enumeration and reference-key helpers
- Existing layout and identity tests

### Out of scope

- Filesystem walk orchestration
- Metadata validation and discovery outcomes
- Candidate selection against remote state
- HTTP or persistence behavior
- New archive layouts or range semantics

## Approach

1. Move layout constants and pure helpers together.
   - Include archive bucket patterns, snapshot patterns, completed-status
     handling, known archive-root names, and supported scan-mode values.
   - Keep path resolution and symlink handling unchanged.

2. Extract range and pruning behavior.
   - Move case-path filters, walk-directory filters, root validation, and
     month-range selection.
   - Preserve current handling for unsupported roots, statusless snapshots,
     non-completed status directories, and month buckets without snapshots.

3. Extract identity and snapshot helpers.
   - Move staging/archive identity normalization.
   - Move snapshot enumeration and execution-to-snapshot reference creation.
   - Keep database-backed checkpoint settlement in discovery until Phase 3,
     because it combines layout references with state and discovery outcomes.

4. Update consumers and tests.
   - Import layout helpers directly from `archive_layout.py`.
   - Patch filesystem functions in `archive_layout.py` when testing their
     runtime lookup.
   - Avoid compatibility wrappers in the NERSC entrypoint unless a real
     external consumer is identified.

## Tests

- Archive bounds accept year and year-month values with unchanged semantics.
- Root pruning selects only eligible month buckets.
- Snapshot pruning keeps completed buckets and supports statusless layouts.
- Unsupported layouts and unreadable roots retain existing error behavior.
- Case identities deduplicate mount, host, staging, and snapshot paths exactly
  as before.
- Snapshot enumeration handles completed, skipped, empty, and late snapshots.
- Run targeted runner tests, `make backend-test`, and `make pre-commit-run`.

## Risk

- Risk score: 4
- Main failure modes:
  - Path resolution or symlink behavior changes while moving helpers.
  - Identity normalization changes deduplication keys.
  - Snapshot helpers split across modules with unclear ownership.

## Open Questions

None.
