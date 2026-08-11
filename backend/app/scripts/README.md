# Scripts

This directory contains standalone operational scripts for the backend application.

These scripts are used for administrative and database-related tasks and are not part of the public API surface.

---

## Structure

Scripts are organized by domain:

```text
scripts/
├── ingestion/
│   ├── archive_client.py
│   ├── archive_discovery.py
│   ├── archive_ingestor_core.py
│   ├── archive_layout.py
│   ├── archive_workflow.py
│   ├── hpc_upload_archive_ingestor.py
│   ├── nersc_archive_ingestor.py
│   ├── sites/
│       └── nersc.sh
│   └── v3_data/
│       ├── __init__.py
│       ├── lcrc-v3.env.example
│       ├── lcrc_v3.sh
│       └── lcrc_v3_archive_ingestor.py
├── db/
│   ├── seed.py
│   ├── rollback_seed.py
│   └── catalog.json
└── users/
    ├── create_admin_account.py
    └── provision_service_account.py
```

### Domains

- **ingestion/** — Scheduled ingestion runners for HPC/performance archive workflows
- **db/** — Database migration, seeding, and rollback utilities
- **users/** — Administrative and service account management

---

## Execution

All scripts must be executed as modules from the project root to ensure proper import resolution.

Example:

```bash
python -m app.scripts.db.seed
python -m app.scripts.db.rollback_seed
python -m app.scripts.users.create_admin_account
python -m app.scripts.ingestion.nersc_archive_ingestor
python -m app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor
```

Do not execute scripts directly by file path:

```bash
# Avoid
python app/scripts/db/seed.py
```

Module execution ensures:

- Correct package imports
- Proper configuration loading
- Consistent environment behavior

---

## Environment Requirements

Scripts depend on:

- Application configuration (`app.core.config`)
- Database configuration (`app.core.database` or `database_async`)
- SQLAlchemy models and services

Before running any script:

1. Ensure required environment variables are set.
2. Ensure the target database is accessible.
3. Confirm you are using the correct environment (local, staging, etc.).

---

## Design Guidelines

When adding new scripts:

- Keep business logic inside `app.features.*` or service modules.
- Keep scripts thin; they should:
  - Initialize configuration
  - Create database sessions if needed
  - Call service-layer functions

- Avoid duplicating application logic.
- Make scripts idempotent where possible.

---

## Scope

These scripts are intended for:

- Development workflows
- Controlled administrative operations
- Environment setup tasks

If operational complexity increases, these scripts may later be consolidated into a structured CLI entrypoint.

---

## NERSC Archive Ingestor

The NERSC archive ingestor scans a bind-mounted performance archive directory,
detects new parseable execution directories, and calls the SimBoard
`/api/v1/ingestions/from-path` API for changed cases. It can scan either the
staging root or the archive root.

Default archive mount path:

- `/performance_archive`

Example:

```bash
SIMBOARD_API_BASE_URL=http://backend:8000 \
MACHINE_NAME=perlmutter \
uv run python -m app.scripts.ingestion.nersc_archive_ingestor
```

Configuration surface (via env vars):

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`
- `SCAN_MODE` (`staging` or `archive`, default `staging`)
- `PERF_ARCHIVE_ROOT` (default `/performance_archive` for `SCAN_MODE=staging`)
- `OLD_PERF_ARCHIVE_ROOT` (default `/OLD_PERF` for `SCAN_MODE=archive`)
- `MACHINE_NAME` (default `perlmutter`)
- `DRY_RUN` (default `true`)
- `MAX_CASES_PER_RUN` (optional, default not set)
- `MAX_ATTEMPTS` (optional, default not set)
- `REQUEST_TIMEOUT_SECONDS` (optional, default 60)
- `ARCHIVE_YEAR_START` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)
- `ARCHIVE_YEAR_END` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)

Helper wrapper:

- `backend/app/scripts/ingestion/sites/nersc.sh` activates `backend/.venv`, sets the documented NERSC staging and archive roots, defaults to `SCAN_MODE=archive`, defaults to `DRY_RUN=true`, and then runs `python -m app.scripts.ingestion.nersc_archive_ingestor`.
- Override `SCAN_MODE`, `DRY_RUN`, or any other supported env var in the caller or cron entry when you need a different schedule or behavior.

Archive notes:

- Archive mode traverses only top-level `YYYY-MM` directories under `OLD_PERF_ARCHIVE_ROOT`. Other top-level directories are ignored.
- Archive scans may include paths without a `COMPLETED/` directory. When snapshot status buckets exist, ingestor scans only `COMPLETED/` and ignores sibling directories in that snapshot bucket.
- Archive dedupe is based on logical case identity plus `execution_id`, not the full timestamped snapshot path.
- `ARCHIVE_YEAR_START` / `ARCHIVE_YEAR_END` are intended for scoped backfills so operators can avoid scanning the full historical tree when unnecessary.
- `YYYY` values expand to full-year bounds (`START=2020` means `2020-01`; `END=2020` means `2020-12`), while `YYYY-MM` values target exact archive month buckets.

## One-Time Chrysalis E3SM v3 Archive Backfill

`v3_data/lcrc_v3_archive_ingestor.py` is a targeted remote-upload backfill for
simulations stored on LCRC Chrysalis and listed in
the [E3SM v3 simulation table](https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/CoupledSystem/simulation_data/simulation_table.html).
It uses a static copy of the table's `Simulation` values, matches archive case
directory leaf names exactly, forces archive scanning from `2024-01`, and
reuses the HPC upload runner's discovery, validation, deduplication, packaging,
and `/api/v1/ingestions/from-hpc-upload` request logic.

For this one-time backfill, copy the committed template outside the repository,
secure it, replace its placeholders, then run a dry run:

```bash
mkdir -p ~/.config/simboard
cp app/scripts/ingestion/v3_data/lcrc-v3.env.example ~/.config/simboard/lcrc-v3.env
chmod 600 ~/.config/simboard/lcrc-v3.env
# Edit ~/.config/simboard/lcrc-v3.env to replace placeholders.
LCRC_V3_ENV_FILE=~/.config/simboard/lcrc-v3.env \
  ./app/scripts/ingestion/v3_data/lcrc_v3.sh
```

`backend/app/scripts/ingestion/v3_data/lcrc_v3.sh` sources the selected
environment file, requires `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`,
and defaults the LCRC archive root and dry-run mode. Set the optional
`OLD_PERF_ARCHIVE_ROOT` in that file only when storage is mounted elsewhere.

Review `v3_case_match`, `v3_case_missing`, and `v3_ingestion_summary` events.
The command exits nonzero when an expected simulation is missing, filesystem
traversal is incomplete, an execution has a transient validation error, or a
live ingestion request fails. Set `DRY_RUN=false` only after every expected
simulation maps to the intended archive case directories.

This targeted runner deliberately ignores database-backed archive snapshot
checkpoints and never writes new ones. A filtered backfill cannot safely mark a
mixed snapshot complete for the general archive runner. Processed execution
state and immutable discovery results still make repeated runs idempotent.

Run this module on Chrysalis, where source case directories are readable. It
requires explicit `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` values for an
externally reachable SimBoard deployment, defaults `OLD_PERF_ARCHIVE_ROOT` to
the documented Chrysalis archive root, and records uploads under machine
`chrysalis`. Retry, timeout, case-limit, dry-run, and optional
`ARCHIVE_YEAR_END` variables remain supported. `SCAN_MODE`,
`ARCHIVE_YEAR_START`, and `MACHINE_NAME` are ignored because source site and
scan scope are fixed.
## Diagnostics Provenance Scanner

`diagnostics_link_scanner` discovers newest paired zppy provenance under the
reviewed, static diagnostics-archive registry and creates case-scoped diagnostic
links through the scanner API. It never reads Mache configuration at runtime.

Run through the NERSC wrapper:

```bash
SIMBOARD_API_TOKEN=<service-account-token> \
DRY_RUN=true \
backend/app/scripts/ingestion/sites/nersc-diagnostics-scanner.sh
```

Required configuration: `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN`, and
`MACHINE_NAME`. The archive root and public URL come only from
`diagnostics_archives.py`. Start with `DRY_RUN=true`; it performs discovery and
state-safe planning without link/state writes. After log review, schedule the
provided cron example with `DRY_RUN=false`.

Scanner account needs read/traverse access to archive `production/` and
`development/` trees, including provenance `.settings` files and published
diagnostic output. Transient network responses are retried; malformed,
output-not-ready, or failed candidates remain unstated and retry next scan.

When a site archive moves, maintainers generate candidate values from Mache
`[web_portal]` cfg data during development, then update the checked-in registry
in a reviewed SimBoard change. Do not add runtime environment overrides for
archive roots or public URLs.

## HPC Upload Archive Ingestor

The HPC upload archive ingestor uses the same scan, state, dry-run, retry, and
per-case submission-state flow as the NERSC path ingestor, but packages each submission-qualified case
directory into a temporary single-case `.tar.gz` archive and calls
`/api/v1/ingestions/from-hpc-upload`.

Both automated runners persist immutable validation results before ingestion.
Results are keyed by machine, normalized case identity, and execution ID with
outcomes `accepted`, `rejected_incomplete`, or `rejected_invalid`. Stored
results bypass later metadata validation. Discovery `accepted` means validation
passed; only successful ingestion adds `processed_execution_ids`. Thus accepted
executions deferred by `MAX_CASES_PER_RUN` or left after failed ingestion remain
future candidates. Typed archive validation errors are immutable content
results, while plain filesystem `OSError` failures and request failures remain
transient and unstored. Persistence is batched, idempotent for exact repeats,
and stops ingestion on failure or conflicting stored outcomes. Dry runs perform
no discovery-result or processed-state writes.

Use this runner when the source filesystem is not directly mounted in the
SimBoard backend environment.

One-case-per-request rule:

- Each upload request contains exactly one case directory.
- `case_path` is sent alongside the archive and becomes the stable case identifier in
  the ingestion audit table.
- Browser/manual uploads still use `/api/v1/ingestions/from-upload`; this runner
  does not call that endpoint.

Example:

```bash
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
```

Configuration surface (via env vars):

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`
- `SCAN_MODE` (`staging` or `archive`, default `staging`)
- `PERF_ARCHIVE_ROOT` (default `/performance_archive` for `SCAN_MODE=staging`)
- `OLD_PERF_ARCHIVE_ROOT` (default `/OLD_PERF` for `SCAN_MODE=archive`)
- `MACHINE_NAME` (default `perlmutter`)
- `DRY_RUN` (default `true`)
- `MAX_CASES_PER_RUN` (optional, default not set)
- `MAX_ATTEMPTS` (optional, default not set)
- `REQUEST_TIMEOUT_SECONDS` (optional, default 60)
- `ARCHIVE_YEAR_START` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)
- `ARCHIVE_YEAR_END` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)

Archive mode uses same `YYYY-MM` top-level bucket requirement described above
for path-based ingestion.
