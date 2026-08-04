# Issue 258 Phased Plan: Archive Ingestion Modules

Issue: [#258 — Split oversized NERSC archive ingestor module](https://github.com/E3SM-Project/simboard/issues/258)

## Task

Split `backend/app/scripts/ingestion/nersc_archive_ingestor.py` into coherent
internal modules while preserving current archive discovery, state, ingestion,
logging, and command-line behavior. Update the HPC upload runner to use shared
modules directly instead of treating the NERSC entrypoint as its library.

## Scope

### In scope

- Shared archive-ingestor types, configuration, and logging contracts
- Archive layout, range, path-filter, case-identity, and snapshot helpers
- Filesystem discovery, validation outcomes, statistics, and candidate selection
- HTTP requests, retries, remote state, discovery-result persistence, and
  archive-checkpoint persistence
- Thin NERSC path-ingestion entrypoint and orchestration module
- HPC upload runner import cleanup required by extracted shared modules
- Existing test updates needed to preserve behavior through each phase

### Out of scope

- API, database schema, or persisted-state format changes
- New dependencies or HTTP libraries
- Archive traversal, deduplication, retry, or checkpoint behavior changes
- Combining both runner loops into one configurable generic runner
- Changes to cron commands, environment variables, endpoints, payloads, log
  event contracts, or process exit codes
- Unrelated ingestion refactors

## Target Boundaries

| Module | Responsibility |
| --- | --- |
| `archive_ingestor_core.py` | Shared types, configuration parsing, stable constants, structured logging, fingerprints, and pure state helpers |
| `archive_layout.py` | Archive ranges, directory pruning, path normalization, case identity, and snapshot enumeration |
| `archive_discovery.py` | Filesystem traversal, metadata validation, discovery outcomes, statistics, scan results, candidates, and snapshot settlement |
| `archive_client.py` | Endpoint construction, HTTP error mapping, request retries, remote state, discovery-result persistence, and checkpoint persistence |
| `archive_workflow.py` | Shared dry-run, candidate-ingestion, completion-summary, and startup-reporting helpers |
| `nersc_archive_ingestor.py` | NERSC path endpoint, path submission, top-level orchestration, `main()`, and module guard |
| `hpc_upload_archive_ingestor.py` | HPC packaging, multipart upload, top-level orchestration, `main()`, and module guard |

Dependency direction must remain acyclic:

```text
runners -> workflow / discovery / client / core
workflow -> discovery / client / core
discovery -> layout / core
client -> core
layout -> core
```

Shared modules must never import either runner entrypoint.

## Approach

Implement each phase as an independently reviewable group. Targeted tests and
full backend tests must pass before starting the next phase.

1. [Phase 1: Shared Contracts and Configuration](phase-1-shared-contracts.md)
   - Establish low-level types, configuration, logging, and state utilities.
   - Preserve both runner entrypoints and runtime contracts.
2. [Phase 2: Archive Layout and Identity](phase-2-archive-layout-and-identity.md)
   - Extract pure path, range, pruning, case-identity, and snapshot helpers.
3. [Phase 3: Discovery and Candidate Selection](phase-3-discovery-and-candidates.md)
   - Extract traversal, validation, discovery outcomes, candidate selection,
     and checkpoint settlement.
4. [Phase 4: HTTP Client and Remote State](phase-4-client-and-state.md)
   - Extract remote-state reads, persistence calls, request handling, and
     retries without changing wire contracts.
5. [Phase 5: Runner Integration and HPC Cleanup](phase-5-runner-integration.md)
   - Extract remaining shared workflow helpers, thin both entrypoints, and
     remove HPC imports from the NERSC module.

Do not leave a phase with temporary duplicate implementations. Move one
responsibility, update all in-repository consumers, then validate it before
continuing.

## Tests

Maintain existing assertions instead of rewriting expected behavior around the
new structure. Update imports and monkeypatch targets to the module where the
runtime lookup occurs.

Run after every phase:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_nersc_archive_ingestor.py \
  tests/features/ingestion/test_hpc_upload_archive_ingestor.py
```

Run before each phase handoff and after Phase 5:

```bash
make backend-test
make pre-commit-run
```

## Risk

- Risk score: 5
- Main failure modes:
  - Imports form cycles between shared types, discovery, client, and workflow.
  - Tests patch re-exported names instead of actual runtime lookup locations.
  - Moving code changes exception classification, request order, retry timing,
    structured log ordering, or exit codes.
  - NERSC and HPC behavior unintentionally converge where they currently differ.
  - A module guard or documented `python -m` entrypoint stops working.

## Open Questions

None.
