# Phase 4 Plan: Provenance Scanner and Operations

## Task

Add a standalone scanner that discovers zppy provenance under each configured
site diagnostics archive, verifies that diagnostics have published output, and
links them to cases with service-account authentication.

The scanner follows the zppy SimBoard publishing contract: diagnostics live
under `diagnostics_archive/<simulation_type>/`, optionally grouped by
`<case_group>/`, and each case directory may contain multiple timestamped
provenance files. The newest timestamped provenance is authoritative.

## Scope

### In scope

- New script `backend/app/scripts/ingestion/diagnostics_link_scanner.py`
- Static diagnostics-archive site registry under `backend/app/scripts/ingestion/`
- Provenance discovery, settings parsing, validation, and published-output checks
- Database-backed provenance state, dry-run behavior, and transient-failure retries
- Scanner-specific diagnostics state API, schema, and migration
- Site-wrapper configuration, scanner tests, and operational documentation

### Out of scope

- Mache runtime/config retrieval
- zppy publishing or provenance-contract changes
- Historical backfill beyond normal scanner operation
- Changes to the existing `POST /api/v1/diagnostics/link` contract or frontend
- Diagnostics content ingestion or interpretation

## Approach

1. Resolve archive locations from a static internal site registry.
   - Add a module under `backend/app/scripts/ingestion/` containing a
     `DIAGNOSTICS_ARCHIVES_BY_MACHINE` dictionary. Each entry contains the
     complete diagnostics archive root and matching public archive base URL.
   - Seed the checked-in dictionary by parsing Mache's
     `mache/machines/*.cfg` files during development, retaining machines with
     non-empty `[web_portal] base_path` and `base_url`, then appending the
     `diagnostics_archive` path component. This is a deliberate development or
     maintenance operation, never a scanner runtime dependency.
   - Key the registry by SimBoard's accepted machine names and aliases, not
     solely Mache cfg filenames. Map machine aliases with the same published
     archive to one registry entry.
   - Select the registry entry from `MACHINE_NAME`. Fail before scanning for an
     unsupported machine; do not accept archive locations from environment
     variables or fetch Mache configuration at runtime.
   - Validate that the selected filesystem root is absolute and readable and
     that the public base URL uses HTTP or HTTPS before scanning.
   - Treat registry values as deliberate source-controlled site configuration:
     refresh the dictionary through a reviewed SimBoard change when a site moves
     its published archive.

2. Discover case provenance within one bounded archive.
   - Scan only the configured root's `production/` and `development/`
     subdirectories.
   - Support both `<simulation_type>/<case>/` and
     `<simulation_type>/<case_group>/<case>/` layouts.
   - Traverse only inside the configured archive root; do not follow symlinks
     outside it. Use a normalized archive-relative case-directory path for
     scanner-state identity.
   - Find only `provenance.<timestamp>.cfg` files with a valid zppy timestamp
     in case directories; order candidates by that parsed timestamp, not file
     modification time.
   - Select the newest timestamp for each case and require a matching
     `provenance.<timestamp>.settings` file.
   - If the newest pair is incomplete, defer that case instead of falling back
     to older provenance.

3. Parse and validate the selected provenance pair.
   - Read `case_name`, `machine`, `hpc_username`, optional `case_group`, and
     authoritative `diagnostics_url` only from the settings file. The cfg
     exists only to establish a matching timestamped provenance pair.
   - Parse settings as bounded UTF-8 `key = value` lines without evaluation;
     reject malformed input and duplicate required keys.
   - Require all case-identity fields needed by `POST /api/v1/diagnostics/link`.
   - Verify the provenance case and optional case group agree with the archive
     layout.
   - Parse `diagnostics_url` and require an exact scheme, authority, and path
     boundary under the configured `DIAGNOSTICS_ARCHIVE_BASE_URL`; never
     derive or accept an unrelated URL.
   - Log and skip malformed or unsafe provenance without terminating the full
     scan.

4. Verify published diagnostic output before linking.
   - Require the published case directory to contain at least one
     non-provenance diagnostic artifact or a non-empty diagnostic subdirectory.
   - Do not inspect zppy status files: they are not published archive artifacts
     and are not a reliable completion signal for one timestamped provenance
     pair.
   - Treat published-output presence as a readiness check, not proof that every
     zppy task has completed.

5. Read and update scanner state through a scanner-specific diagnostics API.
   - Read the database-backed state for the configured machine before submitting
     a candidate. Compare the selected settings filename and fingerprint with
     the state for its archive-relative case-directory path.
   - Skip a candidate whose selected settings filename and fingerprint already
     match successful state.
   - Build the scanner endpoint from `SIMBOARD_API_BASE_URL`. Keep the existing
     `POST /api/v1/diagnostics/link` contract unchanged; add a separate internal
     scanner endpoint that accepts the diagnostics-link payload plus provenance
     source metadata.
   - Authenticate with bearer token from `SIMBOARD_API_TOKEN`.
   - Submit the provenance identity, one diagnostics item with
     `name="zppy diagnostics"`, the authoritative `diagnostics_url`, and
     `kind="diagnostic"`, plus the archive-relative case path, selected settings
     filename, timestamp, and fingerprint.
   - Treat HTTP 204 as success.
   - Retry network failures, HTTP 408/429, and 5xx responses with bounded
     backoff. Do not retry permanent 4xx responses within the same run.
   - The scanner endpoint must atomically upsert the case-scoped link and its
     successful provenance state. Leave failed and output-not-ready candidates
     without successful state so a later scan retries them.

6. Persist central successful provenance state.
   - Add a `DiagnosticProvenanceState` record for each scanner-managed
     diagnostic link. Key the record by canonical machine and normalized
     archive-relative case-directory path, which includes the simulation type
     and optional case group.
   - Store the selected settings filename, parsed timestamp, content fingerprint,
     linked URL, and successful submission timestamp.
   - Link state to its scanner-managed `ExternalLink` with a unique foreign key
     using `ON DELETE CASCADE`. Deleting that link removes or invalidates its
     state; a later scan can recreate the still-published link.
   - Use a database uniqueness constraint and one transaction for the link
     upsert and state upsert so concurrent scanners are safe.
   - Development and production directory paths may create distinct diagnostic
     links for the same SimBoard case. The scanner never removes obsolete links;
     operators remove them manually.
   - In dry-run mode, state reads are allowed, but make no link or state writes.

7. Document and expose site operation.
   - Update `backend/app/scripts/README.md` with configuration, dry-run rollout,
     retry behavior, database-state handling, and example scheduled invocation.
   - Add scanner execution to supported site wrappers without moving scanning
     logic into shell.
   - Document required shared-archive permissions, including scanner read access
     to provenance settings.
   - Explain how maintainers add or refresh a machine entry in the static site
     registry from Mache cfg data.

## Tests

- Add `backend/tests/features/ingestion/test_diagnostics_link_scanner.py`
  covering:
  - static site-registry selection by canonical machine name and alias
  - rejection of unsupported machines
  - valid and invalid registry filesystem roots and public URLs
  - registry generation from representative Mache cfg files, including skipped
    files with missing `[web_portal]` values
  - production and development discovery
  - grouped and ungrouped case layouts
  - newest-timestamp selection
  - missing newest settings file without stale fallback
  - settings-only identity and URL parsing, including malformed and duplicate
    required settings keys
  - case-directory and case-group mismatch rejection
  - diagnostics URL scheme, authority, and path-boundary validation
  - published diagnostic output, empty output, and provenance-only directories
  - exact scanner API payload and bearer authentication
  - transient retries and permanent response handling
  - database-state lookup, successful-state deduplication, and changed-settings
    reprocessing
  - atomic link-and-state persistence, concurrent submissions, and cascade state
    removal when a scanner-managed link is deleted
  - retry after output-not-ready or failed submissions
  - dry-run behavior with no link or state writes

- Run:
  - `make backend-test`
  - `make pre-commit-run`

## Risk

- Risk score: 5
- Main failure modes:
  - Static registry becomes stale after a site moves its published archive
    location.
  - zppy provenance settings format changes before its publishing contract is
    finalized.
  - Published output appears before every zppy task finishes; this MVP links
    published diagnostics rather than proving complete zppy execution.
  - Archive permissions prevent the scanner from reading provenance settings.
  - State identity or transaction logic suppresses needed retries or records a
    link without matching successful provenance state.

## Open Questions

None.
