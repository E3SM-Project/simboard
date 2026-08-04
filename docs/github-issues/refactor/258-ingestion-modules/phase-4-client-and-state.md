# Phase 4 Plan: HTTP Client and Remote State

## Task

Extract endpoint construction, HTTP request handling, remote-state reads,
persistence calls, and retry logic into a shared client module without changing
wire formats or failure behavior.

## Scope

### In scope

- New `backend/app/scripts/ingestion/archive_client.py`
- API base URL normalization and shared endpoint builders
- Path-ingestion request implementation
- Remote ingestion-state and archive-checkpoint reads
- Discovery-result and archive-checkpoint writes
- Retry and transient-status handling
- Remote-state response normalization
- Existing HTTP, state, persistence, and retry tests

### Out of scope

- HPC archive packaging and multipart upload
- API endpoint or payload changes
- New HTTP dependencies
- Retry policy, timeout, batching, or status-code changes
- Runner orchestration ordering

## Approach

1. Move shared endpoint and error handling.
   - Move API-base normalization, state endpoint, discovery-results endpoint,
     checkpoint endpoint, transient-status classification, and request errors.
   - Keep path-ingestion endpoint and request in this module; keep the HPC
     upload endpoint and multipart request in the HPC runner.

2. Move remote-state reads and normalization.
   - Preserve authorization headers, query parameters, timeouts, JSON parsing,
     and sanitization of malformed case and discovery-result entries.

3. Move persistence operations.
   - Preserve discovery-result batching and consume precedence deduplication
     from `archive_ingestor_core.py`.
   - Preserve checkpoint request payloads and no-op handling for empty sets.
   - Keep dry runs from calling persistence functions.

4. Move retry helpers.
   - Preserve attempt counts, backoff, transient/non-transient decisions, and
     exhausted-retry results.
   - Keep injectable sleep and request callables for deterministic tests.

5. Update both runners and tests.
   - Import client operations directly from `archive_client.py`.
   - Patch `urllib.request.urlopen` in the client module for shared request
     tests and in the HPC runner for multipart-upload tests.
   - Do not alter `_run_ingestor` call order in either runner.

## Tests

- URL builders retain current `/api/v1` normalization and endpoint paths.
- Success, HTTP error, URL error, timeout, and invalid JSON behavior stays
  unchanged.
- State normalization retains valid data and sanitizes malformed data.
- Discovery and checkpoint writes retain payloads, batching, idempotency, and
  retry behavior.
- Path ingestion keeps existing request body and processed-execution IDs.
- HPC upload tests continue proving multipart transport independently.
- Run targeted runner tests, `make backend-test`, and `make pre-commit-run`.

## Risk

- Risk score: 5
- Main failure modes:
  - Request headers, payload shape, endpoint paths, or timeout values drift.
  - Error wrapping changes transient classification or retry count.
  - Tests patch the old runner-local `urllib` lookup.
  - Discovery-result precedence changes during helper movement.

## Open Questions

None.
