# Phase 4 Plan: Provenance Scanner and Ops Docs

## Task

Add standalone scanner that discovers zppy provenance cfg files from configured NERSC roots, verifies completion markers, and calls internal diagnostics-link API with service-account auth.

## Scope

### In scope

- New script `backend/app/scripts/ingestion/diagnostics_link_scanner.py`
- State-file persistence and retry behavior
- Provenance cfg parsing and completion checks
- Script test coverage
- Script documentation and env example updates

### Out of scope

- zppy repo changes
- Historical backfill tooling beyond normal scanner behavior
- New backend endpoint behavior outside Phase 2 contract

## Approach

1. Mirror existing operational script structure.
   - Base new script on patterns from `backend/app/scripts/ingestion/nersc_archive_ingestor.py`.
   - Reuse same style for config parsing, structured logs, dry-run handling, retry/backoff, and state persistence.

2. Discover provenance cfg files.
   - Recursively search configured roots from required env var `ZPPY_PROVENANCE_ROOTS`.
   - Accept files matching `provenance*.cfg`.

3. Parse required fields from each cfg.
   - Require `case_name`, `machine`, `hpc_username`, `diagnostic_url`, and `output`.
   - Also extract `www` from the provenance cfg for preserved diagnostics provenance context.
   - Do not derive `diagnostic_url` from `www` in MVP; continue treating explicit `diagnostic_url` as authoritative.
   - Treat missing required fields as terminal skip with structured log.

4. Verify diagnostics completion before linking.
   - Require `<output>/index.html` to exist.
   - Require every filename listed in env var `DIAGNOSTICS_REQUIRED_STATUS_FILES` to exist under `<output>`.
   - Skip incomplete diagnostics without calling API.

5. Call internal diagnostics-link API.
   - Send bearer token from `SIMBOARD_API_TOKEN`.
   - POST one diagnostics-link request per eligible cfg to `POST /api/v1/diagnostics/link`.
   - Use one diagnostics item for MVP: `name="zppy diagnostics"`, `url=diagnostic_url`, `kind="diagnostic"`.

6. Persist scanner state.
   - Store state in `DIAGNOSTICS_STATE_PATH`.
   - Key by provenance file path.
   - Persist cfg fingerprint, last outcome, and timestamp.
   - Reprocess only when cfg fingerprint changes.

7. Document operational config.
   - Update `backend/app/scripts/README.md` with purpose, env vars, and example invocation.
   - Add placeholders to `.envs/example/backend.env.example` only for operator-provided values required by this script.

## Tests

- Add `backend/tests/features/ingestion/test_diagnostics_link_scanner.py` covering:
  - provenance discovery
  - cfg parsing success and failure
  - `www` extraction when present
  - missing required identity or URL
  - completion-marker checks
  - dry-run behavior
  - retry behavior for transient API failures
  - state dedup and retry-on-fingerprint-change
  - API payload formatting
- Run:
  - `make backend-test`
  - `make pre-commit-run`

## Risk

- Risk score: 5
- Main failure modes:
  - Completion-marker policy is too strict or too loose.
  - State logic suppresses needed retries or replays unchanged cfgs.

## Open Questions

None.
