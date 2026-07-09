# Scripts

This directory contains standalone operational scripts for the backend application.

These scripts are used for administrative and database-related tasks and are not part of the public API surface.

---

## Structure

Scripts are organized by domain:

```text
scripts/
├── ingestion/
│   ├── nersc_archive_ingestor.py
│   └── sites/
│       └── nersc.sh
├── db/
│   ├── seed.py
│   ├── rollback_seed.py
│   └── simulations.json
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
- `REQUEST_TIMEOUT_SECONDS` (optional, default 3)
- `ARCHIVE_YEAR_START` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)
- `ARCHIVE_YEAR_END` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)

Helper wrapper:

- `backend/app/scripts/ingestion/sites/nersc.sh` activates `backend/.venv`, sets the documented NERSC staging and archive roots, defaults to `SCAN_MODE=archive`, defaults to `DRY_RUN=true`, and then runs `python -m app.scripts.ingestion.nersc_archive_ingestor`.
- Override `SCAN_MODE`, `DRY_RUN`, or any other supported env var in the caller or cron entry when you need a different schedule or behavior.

Archive notes:

- Archive scans may include paths without a `COMPLETED/` directory. When snapshot status buckets exist, ingestor scans only `COMPLETED/` and ignores sibling directories in that snapshot bucket.
- Archive dedupe is based on logical case identity plus `execution_id`, not the full timestamped snapshot path.
- `ARCHIVE_YEAR_START` / `ARCHIVE_YEAR_END` are intended for scoped backfills so operators can avoid scanning the full historical tree when unnecessary.
- `YYYY` values expand to full-year bounds (`START=2020` means `2020-01`; `END=2020` means `2020-12`), while `YYYY-MM` values target exact archive month buckets.

## HPC Upload Archive Ingestor

The HPC upload archive ingestor uses the same scan, state, dry-run, retry, and
per-case submission-state flow as the NERSC path ingestor, but packages each submission-qualified case
directory into a temporary single-case `.tar.gz` archive and calls
`/api/v1/ingestions/from-hpc-upload`.

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
