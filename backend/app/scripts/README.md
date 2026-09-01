# Operational Scripts

This directory contains administrative scripts for database management, account
provisioning, archive ingestion, and diagnostics discovery. These scripts are
internal operational entry points and are not part of the public API.

## Quick Start

### Requirements

Before running a script:

1. Set the required environment variables.
2. Confirm that the target database or API is accessible.
3. Activate the correct local, staging, or production environment.

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

### Diagnostics Provenance Scanner

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
- `MACHINE_NAME=perlmutter`

#### Run It at LCRC

Use `sites/lcrc-diagnostics-scanner.sh` with `MACHINE_NAME=chrysalis`.

`MACHINE_NAME` is required for every invocation. The wrappers do not assign a
default machine.

#### Operational Behavior

- Dry runs require no API URL or token and emit one candidate event per
  discovered link.
- Structured events cover startup configuration, discovery, candidate
  selection, state lookups, retry outcomes, and completion.
- Credentials are never logged.
- Failed or not-ready candidates are retried during the next run.
- Archive roots and public URLs come only from `diagnostics_archives.py`.

#### Required Filesystem Access

The scanner account needs read and traverse access to:

- `production/`
- `development/`
- Provenance settings
- Published output

Refresh registry entries from Mache `[web_portal]` configuration only through a
reviewed code change. Do not add archive-path environment overrides.

## One-Time E3SM v3 Backfills

### Chrysalis Archive Backfill

#### Purpose

`v3_data/lcrc_v3_archive_ingestor.py` performs a targeted remote-upload backfill
for simulations stored on LCRC Chrysalis and listed in the
[E3SM v3 simulation table](https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/CoupledSystem/simulation_data/simulation_table.html).

The runner:

- Uses a static copy of the table's `Simulation` values.
- Matches archive case-directory leaf names exactly.
- Forces archive scanning to start at `2024-01`.
- Reuses the HPC upload runner's discovery, validation, deduplication,
  packaging, and `/api/v1/ingestions/from-hpc-upload` request logic.
- Records uploads under machine `chrysalis`.

Run the module on Chrysalis, where the source case directories are readable and
the SimBoard deployment is externally reachable.

#### Prepare Configuration

Copy the committed template outside the repository, restrict its permissions,
and replace its placeholders:

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
on the API credentials and optional archive-root override.

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

`v3_data/lcrc_v3_hpss_linker.py` links existing Chrysalis cases to the HPSS URLs
documented in the E3SM v3 simulation table. It does not ingest archive data or
read the Chrysalis filesystem.

Run it inside the deployed SimBoard backend container or administrative job with:

- `DATABASE_URL` and the normal backend settings
- Network access to the documentation page, unless `--source-file` is used

It does not require `SIMBOARD_API_BASE_URL` or `SIMBOARD_API_TOKEN`.

#### Matching and Safety Rules

Before changing links, the linker loads the complete set of existing
`chrysalis` cases and reports:

- Documented mappings without a matching case
- Cases with duplicate user-scoped matches

The linker never guesses unresolved records. Matching cases may still be linked
during `--apply`, but `--apply` refuses to make any changes if a documented case
is missing from the loaded Chrysalis case set.

The v3 documentation table also includes `LR_ensemble`, `RRM_ensemble`, and
the symlinked `v3.NARRM_r0125.amip_0101` row. These do not have corresponding
SimBoard Chrysalis cases, so the linker explicitly excludes them from required
case reconciliation and does not create links for them.

#### Dry Run and Apply

The deployment image does not include the repository Makefile, so run the
module directly from `/app`. Review the dry-run reconciliation counts before
applying changes:

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```

After review, apply the links and rerun the dry run to confirm idempotency:

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker --apply
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```

Use a saved table source when outbound documentation access is unavailable:

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker \
  --source-file /path/to/simulation_table.html
```

## Development Guidelines

When adding a script:

- Keep business logic in `app.features.*` or service modules.
- Keep the script focused on configuration, database-session setup, and calls
  into the service layer.
- Avoid duplicating application logic.
- Make operations idempotent where possible.

These scripts support development workflows, controlled administrative
operations, and environment setup. If operational complexity grows, consolidate
them behind a structured CLI entry point.
