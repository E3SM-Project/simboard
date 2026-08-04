# Phase 9 Plan: HTTP Client Simplification

## Task

Reduce repeated HTTP request construction, response decoding, transport-error
mapping, and retry bookkeeping while preserving every endpoint's current wire
and failure contract.

## Scope

### In scope

- `backend/app/scripts/ingestion/archive_client.py`
- Shared low-level request helpers reused by HPC upload only when semantics
  match exactly
- `backend/app/scripts/ingestion/hpc_upload_archive_ingestor.py`
- Client-owned test consolidation in `test_archive_client.py`
- Existing retry, state, persistence, and multipart-upload tests

### Out of scope

- New HTTP dependencies or async requests
- Endpoint, query, header, payload, timeout, batching, or retry-policy changes
- One highly configurable request function covering every special case
- Moving HPC archive creation or multipart encoding into the shared client
- Standardizing intentionally different error text or JSON handling

## Approach

1. Consolidate client-owned tests first.
   - Move remaining state, path-request, transient-status, and retry unit tests
     from the NERSC runner suite into `test_archive_client.py`.
   - Preserve existing assertions for raw `JSONDecodeError` versus wrapped
     `IngestionRequestError` behavior.

2. Separate request creation from request execution.
   - Add small named helpers for authorization headers and JSON `Request`
     construction where request shapes are identical.
   - Keep endpoint-specific payload dictionaries next to their endpoint
     functions so wire contracts remain readable.

3. Extract narrow response and error helpers.
   - Add one helper for reading and decoding an HTTP response body without
     deciding how callers classify invalid JSON.
   - Add common HTTP-error conversion where message, status, and transient
     semantics match.
   - Keep separate URL/timeout wrappers for standard requests and checkpoint
     requests because their current messages differ.
   - Reuse helpers in HPC upload only where doing so removes duplication without
     adding mode flags or transport-specific branches.

4. Simplify retry bookkeeping without hiding control flow.
   - Extract deterministic backoff calculation and repeated failure-event field
     construction.
   - Keep discovery persistence, case ingestion, and checkpoint persistence as
     separate readable loops because they return different result types and log
     different events.
   - Preserve attempt counts, sleep timing, batch boundaries, stop conditions,
     and empty-input no-op behavior.

5. Final readability and compatibility audit.
   - Remove dead helpers and imports made obsolete by the cleanup.
   - Confirm no production lambda, nested helper, `Callable[..., ...]`, or
     avoidable complexity suppression remains in ingestion modules.
   - Confirm operational docs remain correct; update only if code ownership
     changed.

## Tests

- Assert exact URL, query, method, headers, JSON body, multipart body, and
  timeout for every request type.
- Assert success with empty and non-empty response bodies.
- Assert endpoint-specific invalid JSON, HTTP error, URL error, and timeout
  behavior.
- Assert transient and terminal retry attempts, backoff timing, batching,
  sorting, and no-op inputs.
- Run:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_archive_client.py \
  tests/features/ingestion/test_hpc_upload_archive_ingestor.py \
  tests/features/ingestion/test_nersc_archive_ingestor.py
```

```bash
uv run --project backend mypy backend/app/scripts/ingestion
uv run --project backend ruff check backend/app/scripts/ingestion
make backend-test
make pre-commit-run
```

## Risk

- Risk score: 4
- Main failure modes:
  - Helper reuse changes exact request bytes or header casing.
  - Invalid JSON becomes wrapped or unwrapped differently.
  - URL and timeout errors receive different text or transient flags.
  - Retry extraction changes attempts, backoff, batching, or logging.
  - Shared helper placement creates an import from client back to a runner.

## Open Questions

None.
