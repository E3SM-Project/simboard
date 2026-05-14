# Scripts

This directory contains standalone operational scripts for the backend application.

These scripts are used for administrative and database-related tasks and are not part of the public API surface.

---

## Structure

Scripts are organized by domain:

```
scripts/
├── ingestion/
│   ├── hpc_archive_ingestor.py
│   ├── nersc_archive_ingestor.py
│   └── sites/
│       └── chrysalis.sh
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
python -m app.scripts.ingestion.hpc_archive_ingestor
python -m app.scripts.ingestion.nersc_archive_ingestor --dry-run
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

## HPC Archive Ingestor

The scheduler-agnostic HPC archive ingestor is the preferred entrypoint for
site wrappers. It currently delegates to the existing NERSC archive ingestor,
preserving Perlmutter behavior while giving non-NERSC schedulers a stable shared
command.

Example:

```bash
uv run python -m app.scripts.ingestion.hpc_archive_ingestor
```

Thin site wrappers live under `app/scripts/ingestion/sites/`. They should only
set site-specific environment and call the shared ingestor. Ingestion logic
belongs in Python, not in shell wrappers.

### Chrysalis Wrapper

`app/scripts/ingestion/sites/chrysalis.sh` is intended for the existing Sandia
Jenkins workflow. It sets Chrysalis defaults and requires caller-provided
`SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`.

Default Chrysalis archive root:

- `/lcrc/group/e3sm/PERF_Chrysalis/performance_archive`

The wrapper defaults to `DRY_RUN=true`; set `DRY_RUN=false` only after validating
archive access, token storage, network egress, and candidate counts.

Compy, Aurora, and Frontier adapters are intentionally deferred until accounts
or equivalent native-runner access exists for those sites.

## NERSC Archive Ingestor

The NERSC archive ingestor scans a bind-mounted performance archive directory,
detects new parseable execution directories, and calls the SimBoard
`/api/v1/ingestions/from-path` API for changed cases.

Default archive mount path:

- `/performance_archive`

Example:

```bash
uv run python -m app.scripts.ingestion.nersc_archive_ingestor \
  --api-base-url http://backend:8000 \
  --machine-name perlmutter
```

Configuration surface (via env vars):

- `SIMBOARD_API_BASE_URL` (`--api-base-url`)
- `SIMBOARD_API_TOKEN` (`--api-token`)
- `PERF_ARCHIVE_ROOT` (`--archive-root`, default `/performance_archive`)
- `MACHINE_NAME` (`--machine-name`, default `perlmutter`)
- `STATE_PATH` (`--state-path`)
- `DRY_RUN` (`--dry-run`)
- `MAX_CASES_PER_RUN` (`--max-cases-per-run`)
- `MAX_ATTEMPTS` (`--max-attempts`)
- `REQUEST_TIMEOUT_SECONDS` (`--request-timeout-seconds`)
