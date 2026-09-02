# Operational Scripts

This directory contains administrative scripts for database management, account
provisioning, archive ingestion, and diagnostics discovery. These scripts are
internal operational entry points and are not part of the public API.

## Quick Start

### Requirements

Before running a script:

Scripts are organized by domain:

```text
scripts/
├── ingestion/
│   ├── archive_client.py
│   ├── archive_discovery.py
│   ├── archive_ingestor_core.py
│   ├── archive_layout.py
│   ├── archive_workflow.py
│   ├── diagnostics_archives.py
│   ├── diagnostics_link_scanner.py
│   ├── hpc_upload_archive_ingestor.py
│   ├── nersc_archive_ingestor.py
│   ├── sites/
│   │   ├── lcrc-diagnostics-scanner.sh
│   │   ├── nersc-diagnostics-scanner.sh
│   │   ├── site_ingestion_launcher.sh
│   │   ├── chrysalis.config
│   │   └── nersc.config
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

Scripts may depend on:

- Application configuration from `app.core.config`
- Database configuration from `app.core.database` or `database_async`
- SQLAlchemy models and application services

### Run Scripts as Modules

Run all scripts as modules from the project root. This ensures correct package
imports, configuration loading, and environment behavior.

```bash
python -m app.scripts.db.seed
python -m app.scripts.db.rollback_seed
python -m app.scripts.users.create_admin_account
python -m app.scripts.ingestion.hpc_upload_archive_ingestor
python -m app.scripts.ingestion.nersc_archive_ingestor
python -m app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```

Do not execute scripts directly by file path:

```bash
# Avoid
python app/scripts/db/seed.py
```

## Script Directory

Scripts are organized by domain:

| Domain       | Purpose                                                          |
| ------------ | ---------------------------------------------------------------- |
| `ingestion/` | Scheduled ingestion, archive backfill, and diagnostics workflows |
| `db/`        | Database seeding and rollback utilities                          |
| `users/`     | Administrative and service-account management                    |

The primary operational entry points are:

| Workflow                 | Entry point                           | Purpose                                           |
| ------------------------ | ------------------------------------- | ------------------------------------------------- |
| NERSC archive ingestion  | `nersc_archive_ingestor.py`           | Ingest cases from a backend-mounted archive       |
| HPC upload ingestion     | `hpc_upload_archive_ingestor.py`      | Package and upload cases from a remote HPC system |
| Diagnostics scanning     | `diagnostics_link_scanner.py`         | Discover and create case-scoped diagnostic links  |
| E3SM v3 archive backfill | `v3_data/lcrc_v3_archive_ingestor.py` | Backfill selected Chrysalis simulations           |
| E3SM v3 HPSS linking     | `v3_data/lcrc_v3_hpss_linker.py`      | Add documented HPSS URLs to existing cases        |

## Common Ingestion Behavior

The NERSC path-based and HPC upload ingestors share archive discovery,
validation, deduplication, state tracking, dry-run, retry, and per-case
submission behavior.

### Scan Modes

| Mode      | Root variable           | Default root           | Purpose                           |
| --------- | ----------------------- | ---------------------- | --------------------------------- |
| `staging` | `PERF_ARCHIVE_ROOT`     | `/performance_archive` | Scan the current staging archive  |
| `archive` | `OLD_PERF_ARCHIVE_ROOT` | `/OLD_PERF`            | Scan historical archive snapshots |

Archive mode has these constraints:

- Only top-level `YYYY-MM` directories are traversed. Other directories are
  ignored.
- When a snapshot contains status buckets, only `COMPLETED/` is scanned.
- Archives without a `COMPLETED/` directory remain supported.
- Deduplication uses logical case identity and `execution_id`, not the full
  timestamped snapshot path.
- `ARCHIVE_YEAR_START` and `ARCHIVE_YEAR_END` can limit historical backfills.
  Each value accepts `YYYY` or `YYYY-MM`.
- A year expands to its full boundary: `START=2020` means `2020-01`, and
  `END=2020` means `2020-12`.

### Validation and State

Both automated ingestors persist immutable validation results before ingestion:

- Results are keyed by machine, normalized case identity, and execution ID.
- Stored outcomes are `accepted`, `rejected_incomplete`, or `rejected_invalid`.
- Stored results bypass metadata validation on later runs.
- An `accepted` result means validation passed. Only successful ingestion adds
  the execution to `processed_execution_ids`.
- Accepted executions deferred by `MAX_CASES_PER_RUN` or left after a failed
  request remain eligible for a future run.
- Typed archive-validation errors are stored as immutable content results.
- Filesystem `OSError` failures and request failures are transient and are not
  stored.
- Persistence is batched and idempotent for exact repeats. A persistence failure
  or conflicting stored outcome stops ingestion.
- Dry runs do not write discovery results or processed state.

### Common Environment Variables

| Variable                  | Required  | Default                | Purpose                                  |
| ------------------------- | --------- | ---------------------- | ---------------------------------------- |
| `SIMBOARD_API_BASE_URL`   | Live runs | None                   | SimBoard API endpoint                    |
| `SIMBOARD_API_TOKEN`      | Live runs | None                   | Service-account token                    |
| `SCAN_MODE`               | No        | `staging`              | Select staging or archive scanning       |
| `PERF_ARCHIVE_ROOT`       | No        | `/performance_archive` | Staging archive root                     |
| `OLD_PERF_ARCHIVE_ROOT`   | No        | `/OLD_PERF`            | Historical archive root                  |
| `MACHINE_NAME`            | No        | `perlmutter`           | Source machine recorded during ingestion |
| `DRY_RUN`                 | No        | `true`                 | Prevent ingestion and state changes      |
| `MAX_CASES_PER_RUN`       | No        | Unlimited              | Limit submissions per invocation         |
| `MAX_ATTEMPTS`            | No        | Unlimited              | Limit request attempts                   |
| `REQUEST_TIMEOUT_SECONDS` | No        | `60`                   | Set the request timeout in seconds       |
| `ARCHIVE_YEAR_START`      | No        | None                   | Earliest archive month to scan           |
| `ARCHIVE_YEAR_END`        | No        | None                   | Latest archive month to scan             |

## Ingestion Workflows

### NERSC Path-Based Archive Ingestion

#### When to Use It

Use the NERSC archive ingestor when the performance archive is bind-mounted in
the SimBoard backend environment. It scans for new parseable execution
directories and calls `/api/v1/ingestions/from-path` for changed cases.

#### Run It

```bash
SIMBOARD_API_BASE_URL=http://backend:8000 \
MACHINE_NAME=perlmutter \
uv run python -m app.scripts.ingestion.nersc_archive_ingestor
```

#### NERSC Wrapper

`backend/app/scripts/ingestion/sites/nersc.sh`:

- Activates `backend/.venv`
- Sets the documented NERSC staging and archive roots
- Defaults to `SCAN_MODE=archive`
- Defaults to `DRY_RUN=true`
- Runs `python -m app.scripts.ingestion.nersc_archive_ingestor`

Override `SCAN_MODE`, `DRY_RUN`, or another supported variable in the calling
environment or cron entry when a different behavior is required.

### HPC Upload Archive Ingestion

#### When to Use It

Use the HPC upload ingestor when the source filesystem is not mounted in the
SimBoard backend environment. It packages each submission-qualified case as a
temporary `.tar.gz` archive and calls
`/api/v1/ingestions/from-hpc-upload`.

#### Run It

```bash
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
```

The common ingestion environment variables and archive rules apply.

#### Upload Rules

- Each request contains exactly one case directory.
- `case_path` is sent with the archive and becomes the stable case identifier in
  the ingestion audit table.
- Browser and manual uploads continue to use
  `/api/v1/ingestions/from-upload`. This runner does not call that endpoint.

## HPC Upload Archive Ingestor

The scheduler-agnostic HPC upload archive ingestor is the preferred entrypoint for
site wrappers. It currently delegates to the existing NERSC archive ingestor,
preserving Perlmutter behavior while giving non-NERSC schedulers a stable shared
command.

Example:

```bash
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
```

### Site Collection Launcher

`app/scripts/ingestion/sites/site_ingestion_launcher.sh` is the host-side
launcher for site collection. It loads `sites/<site>.config`, then selects the
configured Python ingestor. Use it as:

```bash
app/scripts/ingestion/sites/site_ingestion_launcher.sh nersc staging
app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis archive
```

Each site config defines its machine name, archive roots, working and repository
paths, Python environment file, token export file, API base URL, archive lower
bound, and ingestor module. The launcher defaults to `DRY_RUN=true` with
`DRY_RUN_USE_REMOTE_STATE=true`, so it loads API credentials and performs
read-only state validation. Set `DRY_RUN_USE_REMOTE_STATE=false` for a
credential-free offline scan. Set `DRY_RUN=false` only after validating archive
access, token storage, network egress, and candidate counts. A capped
`MAX_CASES_PER_RUN` value limits real ingestion but still persists results.

Site configs are operational inputs. Keep credentials in their referenced,
protected files rather than committing them to a config file.

## NERSC Archive Ingestor

#### When to Use It

Use the diagnostics scanner to find the newest paired zppy provenance from the
reviewed static registry and create case-scoped diagnostic links. The scanner
does not read Mache configuration at runtime.

#### Run It at NERSC

Start with a dry run:

```bash
MACHINE_NAME=perlmutter \
DRY_RUN=true \
backend/app/scripts/ingestion/sites/nersc-diagnostics-scanner.sh
```

After reviewing the logs, run or schedule it with `DRY_RUN=false` and provide:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`
- `SCAN_MODE` (`staging` or `archive`, default `staging`)
- `PERF_ARCHIVE_ROOT` (default `/performance_archive` for `SCAN_MODE=staging`)
- `OLD_PERF_ARCHIVE_ROOT` (default `/OLD_PERF` for `SCAN_MODE=archive`)
- `MACHINE_NAME` (default `perlmutter`)
- `DRY_RUN` (default `true`)
- `DRY_RUN_USE_REMOTE_STATE` (default `true`; set `false` for offline dry runs)
- `MAX_CASES_PER_RUN` (optional, default not set)
- `MAX_ATTEMPTS` (optional, default not set)
- `REQUEST_TIMEOUT_SECONDS` (optional, default 60)
- `ARCHIVE_YEAR_START` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)
- `ARCHIVE_YEAR_END` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)

Archive notes:

- Archive mode traverses only top-level `YYYY-MM` directories under `OLD_PERF_ARCHIVE_ROOT`. Other top-level directories are ignored.
- Archive scans may include paths without a `COMPLETED/` directory. When snapshot status buckets exist, ingestor scans only `COMPLETED/` and ignores sibling directories in that snapshot bucket.
- Archive dedupe is based on logical case identity plus `execution_id`, not the full timestamped snapshot path.
- Direct Python entrypoints leave `ARCHIVE_YEAR_START` / `ARCHIVE_YEAR_END` unset. The site collection launcher applies each site's configured archive lower bound; callers may override either bound for a differently scoped archive scan.
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
cp app/scripts/ingestion/v3_data/lcrc-v3.env.example \
  ~/.config/simboard/lcrc-v3.env
chmod 600 ~/.config/simboard/lcrc-v3.env

# Edit ~/.config/simboard/lcrc-v3.env and replace its placeholders.
```

The environment file must define:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`

Set `OLD_PERF_ARCHIVE_ROOT` only when the Chrysalis archive is mounted somewhere
other than its documented default.

#### Run from the Repository Root

Start with the Make dry run:

```bash
make v3-ingest-dry-run LCRC_V3_ENV_FILE=~/.config/simboard/lcrc-v3.env
```

Review these events:

- `v3_case_match`
- `v3_case_missing`
- `v3_ingestion_summary`

The dry run exits nonzero when:

- An expected simulation is missing.
- Filesystem traversal is incomplete.
- An execution has a transient validation error.
- A simulated live-ingestion request would fail.

After every expected simulation maps to the intended archive case directory,
run the explicit apply target:

```bash
make v3-ingest-apply LCRC_V3_ENV_FILE=~/.config/simboard/lcrc-v3.env
```

The Make targets override `DRY_RUN`; keep the external environment file focused
on the API credentials and optional archive-root override. They run Python with
unbuffered output so emitted structured events appear in the console immediately.

#### Fixed and Supported Settings

The source site and scan scope are fixed. The runner ignores:

- `SCAN_MODE`
- `ARCHIVE_YEAR_START`
- `MACHINE_NAME`

The following controls remain supported:

- `MAX_ATTEMPTS`
- `MAX_CASES_PER_RUN`
- `REQUEST_TIMEOUT_SECONDS`
- `ARCHIVE_YEAR_END`

#### State Behavior

This targeted runner does not read or write database-backed archive snapshot
checkpoints. A filtered backfill cannot safely mark a mixed snapshot as complete
for the general archive runner. Processed-execution state and immutable
discovery results still make repeated runs idempotent.

### E3SM v3 HPSS Linker

#### Purpose

`v3_data/lcrc_v3_hpss_linker.py` links existing Chrysalis and Perlmutter cases
to the HPSS URLs documented in the E3SM v3 simulation table. It does not ingest
archive data or read the Chrysalis filesystem.

Run it inside the deployed SimBoard backend container or administrative job with:

- `DATABASE_URL` and the normal backend settings
- Network access to the documentation page, unless `--source-file` is used

It does not require `SIMBOARD_API_BASE_URL` or `SIMBOARD_API_TOKEN`.

#### Matching and Safety Rules

Before changing links, the linker loads the complete set of existing
`chrysalis` and `perlmutter` cases and reports:

- Documented mappings without a matching case
- Cases with duplicate user-scoped matches

Its summary also separates matching and unmapped case counts by machine. This
allows the Perlmutter-owned `v3.LR.amip_bonus_0101` case to receive its HPSS
link without adding it to the Chrysalis-targeted archive backfill.

The linker never guesses unresolved records. `--apply` refuses to make any
changes if a documented case is missing from the loaded Chrysalis case set. The
targeted v3 archive backfill includes all documented v3 case entries, including
the ensemble and symlinked NARRM rows, so run that backfill before linking.

#### Dry Run and Apply

The deployment image does not include the repository Makefile, so run the
module directly from `/app`. Review the dry-run reconciliation counts before
applying changes:

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```

After review, apply the links and rerun the dry run to confirm idempotency:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`
- `SCAN_MODE` (`staging` or `archive`, default `staging`)
- `PERF_ARCHIVE_ROOT` (default `/performance_archive` for `SCAN_MODE=staging`)
- `OLD_PERF_ARCHIVE_ROOT` (default `/OLD_PERF` for `SCAN_MODE=archive`)
- `MACHINE_NAME` (default `perlmutter`)
- `DRY_RUN` (default `true`)
- `DRY_RUN_USE_REMOTE_STATE` (default `true`; set `false` for offline dry runs)
- `MAX_CASES_PER_RUN` (optional, default not set)
- `MAX_ATTEMPTS` (optional, default not set)
- `REQUEST_TIMEOUT_SECONDS` (optional, default 60)
- `ARCHIVE_YEAR_START` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)
- `ARCHIVE_YEAR_END` (optional, archive mode only; accepts `YYYY` or `YYYY-MM`)

Archive mode uses same `YYYY-MM` top-level bucket requirement described above
for path-based ingestion.
