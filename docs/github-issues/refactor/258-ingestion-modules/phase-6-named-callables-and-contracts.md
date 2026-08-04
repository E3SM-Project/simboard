# Phase 6 Plan: Named Callables and Explicit Contracts

## Task

Remove anonymous and nested production callables that obscure control flow.
Replace broad callback annotations with named, precise contracts while keeping
all runtime behavior unchanged.

## Scope

### In scope

- `backend/app/scripts/ingestion/archive_ingestor_core.py`
- `backend/app/scripts/ingestion/archive_layout.py`
- `backend/app/scripts/ingestion/archive_discovery.py`
- `backend/app/scripts/ingestion/archive_client.py`
- `backend/app/scripts/ingestion/archive_workflow.py`
- `backend/app/scripts/ingestion/hpc_upload_archive_ingestor.py`
- Existing callback, filtering, sorting, multipart, and runner tests

### Out of scope

- Changing discovery, filtering, sorting, multipart, or retry behavior
- Decomposing large discovery or runner functions; later phases handle that
- A generic callback registry, dependency container, or runner framework
- New dependencies or public interfaces

## Approach

1. Lock current callable behavior with existing tests.
   - Preserve archive-range filtering, traversal-error logging, deterministic
     candidate sorting, multipart field order, request injection, and retry
     injection.
   - Keep monkeypatch targets at actual runtime lookup locations.

2. Replace anonymous production callables with named module-level helpers.
   - Replace the returned case-path lambda in `archive_layout.py` with a named
     predicate bound through `functools.partial`.
   - Replace the candidate sorting lambda in `archive_discovery.py` with a named
     sort-key function.
   - Do not replace straightforward test lambdas unless a moved runtime lookup
     requires it.

3. Move nested production helpers to module level.
   - Replace `_scan_archive()`'s nested walk-error callback with a named helper
     whose scan context is bound explicitly.
   - Replace `_encode_multipart_form_data()`'s nested text-part writer with a
     small module-level byte-buffer helper.
   - Preserve callback invocation timing, captured state mutation, multipart
     boundary use, and field ordering.

4. Define precise callback protocols.
   - Add separate callable protocols for case submission, discovery-result
     persistence, checkpoint persistence, metadata location, sleeping, and
     structured logging where those signatures cross module boundaries.
   - Replace touched `Callable[..., IngestionRequestResponse]` annotations.
   - Keep protocols structural and internal; do not add wrapper classes solely
     to satisfy typing.

5. Run formatting, lint, typing, and regression checks.
   - Confirm no new import cycle from protocol ownership.
   - Confirm production modules no longer contain lambdas or nested helper
     functions except methods defined inside classes.

## Tests

- Retain existing archive layout, discovery, HPC multipart, retry, and runner
  assertions unchanged.
- Add direct tests only when a new named helper contains meaningful branching;
  otherwise test through its existing caller.
- Run:

```bash
cd backend
uv run pytest -q \
  tests/features/ingestion/test_archive_client.py \
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

- Risk score: 2
- Main failure modes:
  - A bound named helper receives arguments in a different order than the old
    lambda or closure.
  - Moving closure state to explicit arguments stops mutating the live scan
    object or multipart buffer.
  - Protocol placement creates a client/core/workflow import cycle.

## Open Questions

None.
