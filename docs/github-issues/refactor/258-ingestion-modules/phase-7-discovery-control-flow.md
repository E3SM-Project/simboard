# Phase 7 Plan: Discovery Control-Flow Simplification

## Task

Make archive discovery readable from top to bottom by separating state lookup,
validation, result recording, counter updates, and log preparation. Preserve
all discovery and checkpoint semantics.

## Scope

### In scope

- `backend/app/scripts/ingestion/archive_discovery.py`
- Small supporting contracts in `archive_ingestor_core.py` when needed
- Discovery, candidate-selection, collection-log, and snapshot-settlement tests
- Ownership-aligned movement of affected tests out of the NERSC runner suite

### Out of scope

- Filesystem traversal algorithm or archive layout changes
- Parser behavior or exception classification changes
- Candidate ordering, limits, identity, deduplication, or checkpoint changes
- HTTP persistence and runner orchestration
- A generalized discovery pipeline or plugin architecture

## Approach

1. Move discovery-owned tests to a focused test module.
   - Create `backend/tests/features/ingestion/test_archive_discovery.py`.
   - Move existing unit tests without rewriting expectations.
   - Leave end-to-end runner behavior in runner test modules.

2. Simplify `_scan_archive()` setup.
   - Extract named helpers for snapshot-scan initialization, selected snapshot
     keys, and traversal callbacks only where they remove branching from the
     main function.
   - Keep scan steps visible in execution order: initialize, walk, build scan
     results, select candidates, log outcomes, return.

3. Decompose `_collect_case_execution()` by decision source.
   - Keep one readable early-return path for already-processed executions.
   - Move stored immutable-outcome handling into a named helper.
   - Move fresh validation and discovery-result recording into a named helper.
   - Centralize accepted-execution recording so grouped results, case log data,
     and counters cannot drift.
   - Reuse existing `ExecutionCollectionDecision` and
     `ExecutionDiscoveryResult`; add no parallel result hierarchy.

4. Separate case outcome calculation from log emission.
   - Extract pure helpers that compute existing, new, selected, deferred, and
     rejected execution sets and decisions for one case.
   - Keep `_log_execution_collection_outcomes()` responsible for ordered event
     emission and cross-case processed-ID updates.
   - Preserve exact event order, field order, counter timing, and case sorting.

5. Remove complexity suppressions only after natural simplification.
   - Delete `# noqa: C901` from `_collect_case_execution()` when it passes the
     configured complexity limit.
   - Do not split functions merely to satisfy a metric if call flow becomes
     harder to follow.

## Tests

- Cover already-processed, stored accepted, stored rejected, fresh accepted,
  incomplete, invalid, transient, and deferred decisions.
- Assert exact discovery counters before and after per-run limiting.
- Assert grouped case log ordering and fields.
- Assert snapshot settlement for processed, immutable rejected, failed,
  transient, deferred, empty, and incomplete-traversal cases.
- Run:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_archive_discovery.py \
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
  - Counter updates happen twice or stop happening on cached outcomes.
  - Stored accepted outcomes unexpectedly invoke metadata validation.
  - Refactoring changes mutation timing used to deduplicate overlapping cases.
  - Log grouping or deterministic execution ordering changes.
  - Snapshot settlement treats transient or failed executions as permanent.

## Open Questions

None.
