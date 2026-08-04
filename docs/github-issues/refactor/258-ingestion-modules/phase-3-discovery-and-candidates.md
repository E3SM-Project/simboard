# Phase 3 Plan: Discovery and Candidate Selection

## Task

Extract archive scanning, execution validation, discovery outcomes, statistics,
candidate construction, and snapshot settlement into a cohesive discovery
module that depends on layout and core contracts.

## Scope

### In scope

- New `backend/app/scripts/ingestion/archive_discovery.py`
- Filesystem walk and progress reporting
- Execution metadata validation and immutable discovery outcomes
- Case scan results and collection decision logs
- Processed-ID lookup and deterministic candidate selection
- Shared discovery-result precedence applied during snapshot settlement
- Archive checkpoint settlement calculation
- Existing discovery, candidate, and checkpoint tests

### Out of scope

- HTTP reads or persistence writes
- Candidate submission and retry behavior
- Changing parser error classification
- Changing case identity, execution identity, limits, or checkpoint rules

## Approach

1. Move scan orchestration and traversal.
   - Move `_scan_archive`, filesystem walk, progress logging, and discovery
     statistics initialization.
   - Consume filters and snapshot helpers from `archive_layout.py`.
   - Preserve walk error handling and archive traversal-complete tracking.

2. Move execution collection and validation.
   - Preserve accepted, rejected-incomplete, rejected-invalid, and transient
     classification.
   - Preserve cached immutable-result bypass behavior.
   - Keep detailed and compacted collection logs unchanged.

3. Move deterministic result and candidate construction.
   - Build sorted scan results and fingerprints.
   - Normalize processed execution IDs by case identity.
   - Select new executions, apply per-run limits, and retain deferred counts.

4. Move settlement calculation.
   - Combine processed state, stored discovery outcomes, new outcomes, and
     snapshot references without performing network writes.
   - Consume immutable-result precedence and deduplication from
     `archive_ingestor_core.py`.
   - Preserve empty, failed, transient, deferred, and traversal-error rules.

5. Update runtime lookup and tests.
   - Inject metadata locator and walk error callbacks as before.
   - Patch `archive_discovery.py` for traversal, logging, and validation unit
     tests.
   - Keep NERSC and HPC orchestration tests proving identical scan inputs.

## Tests

- Complete, incomplete, invalid, unreadable, and transient executions retain
  current outcomes and counters.
- Stored immutable outcomes bypass metadata validation correctly.
- Candidate ordering, deduplication, mixed state, and run limits remain stable.
- Collection and progress logs retain event names, fields, and grouping.
- Snapshot settlement handles successful, rejected, deferred, failed,
  transient, empty, and incomplete traversal cases.
- Run targeted runner tests, `make backend-test`, and `make pre-commit-run`.

## Risk

- Risk score: 5
- Main failure modes:
  - Callback or monkeypatch lookup changes alter test and runtime behavior.
  - Discovery classification changes persisted immutable outcomes.
  - Candidate ordering or case identity application changes idempotency.
  - Settlement marks a snapshot complete before all work is permanent.

## Open Questions

None.
