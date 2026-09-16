# Operational Scripts

This directory contains internal operational entry points for database
management, account provisioning, archive ingestion, and diagnostics discovery.
They are not part of the public API.

## In This Guide

- [Run a script](#run-a-script)
- [Choose an ingestion workflow](#ingestion-workflows)
- [Configure and schedule site collection](#site-collection-launcher)
- [Run the diagnostics scanner](#nersc-diagnostics-link-scanner)
- [Backfill E3SM v3 data](#one-time-chrysalis-e3sm-v3-archive-backfill)
- [Link E3SM v3 HPSS archives](#e3sm-v3-hpss-linker)

## Run a Script

Before running an operational script:

1. Set its required environment variables.
2. Confirm the target database or API is reachable.
3. Select the intended local, staging, or production environment.

Run Python scripts as modules from the backend project root. This preserves
package imports, application configuration, and environment behavior.

```bash
uv run python -m app.scripts.db.seed
uv run python -m app.scripts.db.rollback_seed
uv run python -m app.scripts.users.create_admin_account
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
uv run python -m app.scripts.ingestion.nersc_archive_ingestor
uv run python -m app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor
uv run python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```

> **Do not** execute a Python script directly by file path:

```bash
# Incorrect
uv run python app/scripts/ingestion/nersc_archive_ingestor.py
```

### Script Areas

| Domain       | Purpose                                                          |
| ------------ | ---------------------------------------------------------------- |
| `ingestion/` | Scheduled ingestion, archive backfill, and diagnostics workflows |
| `db/`        | Database seeding and rollback utilities                          |
| `users/`     | Administrative and service-account management                    |

### Primary Entry Points

| Workflow                 | Entry point                           | Purpose                                           |
| ------------------------ | ------------------------------------- | ------------------------------------------------- |
| NERSC archive ingestion  | `nersc_archive_ingestor.py`           | Ingest cases from a backend-mounted archive       |
| HPC upload ingestion     | `hpc_upload_archive_ingestor.py`      | Package and upload cases from a remote HPC system |
| Diagnostics scanning     | `diagnostics_link_scanner.py`         | Discover and create case-scoped diagnostic links  |
| E3SM v3 archive backfill | `v3_data/lcrc_v3_archive_ingestor.py` | Backfill selected Chrysalis simulations           |
| E3SM v3 HPSS linking     | `v3_data/lcrc_v3_hpss_linker.py`      | Add documented HPSS URLs to existing cases        |

## Ingestion Workflows

Choose the runner based on where the archive filesystem is available:

| Archive location | Runner | Submission method |
| --- | --- | --- |
| Mounted in the SimBoard backend environment | `nersc_archive_ingestor.py` | API path submission |
| Available only at a remote HPC site | `hpc_upload_archive_ingestor.py` | Per-case archive upload |

Both runners share archive discovery, validation, deduplication, state tracking,
dry-run, retry, and per-case submission behavior.

## Common Ingestion Behavior

### Scan Modes

| Mode      | Root variable           | Default root           | Purpose                           |
| --------- | ----------------------- | ---------------------- | --------------------------------- |
| `staging` | `PERF_ARCHIVE_ROOT`     | `/performance_archive` | Scan the current staging archive  |
| `archive` | `OLD_PERF_ARCHIVE_ROOT` | `/OLD_PERF`            | Scan historical archive snapshots |

In archive mode:

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

### Environment Variables

**API access**

| Variable | Required | Purpose |
| --- | --- | --- |
| `SIMBOARD_API_BASE_URL` | Live runs and remote-state dry runs | SimBoard API endpoint |
| `SIMBOARD_API_TOKEN` | Live runs and remote-state dry runs | Service-account token |

**Archive selection**

| Variable | Default | Purpose |
| --- | --- | --- |
| `SCAN_MODE` | `staging` | Select staging or archive scanning |
| `PERF_ARCHIVE_ROOT` | `/performance_archive` | Staging archive root |
| `OLD_PERF_ARCHIVE_ROOT` | `/OLD_PERF` | Historical archive root |
| `MACHINE_NAME` | `perlmutter` | Source machine recorded during ingestion |
| `ARCHIVE_YEAR_START` | None | Earliest archive month to scan |
| `ARCHIVE_YEAR_END` | None | Latest archive month to scan |

**Run controls**

| Variable | Default | Purpose |
| --- | --- | --- |
| `DRY_RUN` | `true` | Prevent ingestion and state changes |
| `MAX_CASES_PER_RUN` | Unlimited | Limit submissions per invocation |
| `MAX_ATTEMPTS` | Unlimited | Limit request attempts |
| `REQUEST_TIMEOUT_SECONDS` | `60` | Request timeout in seconds |

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

### Site Collection Launcher

`app/scripts/ingestion/sites/site_ingestion_launcher.sh` is the host-side
launcher for site collection. It loads `sites/<site>.config`, then selects the
configured Python ingestor.

```bash
app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis archive
```

#### Configuration Ownership

| Location | Configure | Notes |
| --- | --- | --- |
| Committed site config | Machine name, archive roots, environment-file default, archive lower bound, ingestor module | Never store credentials here. |
| Standard deployment configuration | `SIMBOARD_ROOT` and protected environment file containing API URL and token | Required for remote API access. |
| Deployment overrides | `SIMBOARD_MODULES`, `SIMBOARD_WORKDIR`, `SIMBOARD_ENV_FILE` | Supports nonstandard layouts and alternate API targets. |

For the standard layout, `SIMBOARD_ROOT` contains both
`repository/simboard/backend` and `operations`. The launcher derives its module
and working paths. The Chrysalis site configuration defaults
`SIMBOARD_ENV_FILE` to
`/lcrc/group/e3sm2/simboard/operations/environment.sh`; a job can override the
path to select another API environment.

The environment file is a group-protected Bash file that exports both
`SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`; every reader in that group
must be authorized to use the token. Initialize a new file from the committed
template without overwriting an existing file:

```bash
make chrysalis-init-environment
make chrysalis-init-environment ENV_FILE=/lcrc/group/e3sm2/simboard/operations/environment.production.sh
```

#### Run Safely

1. Start with the default `DRY_RUN=true`. It also defaults
   `DRY_RUN_USE_REMOTE_STATE=true`, which validates remote state without writing.
2. Use `DRY_RUN_USE_REMOTE_STATE=false` only for a credential-free offline scan.
3. Confirm archive access, token storage, network egress, and candidate counts.
4. Set `DRY_RUN=false` only after that review. Use `MAX_CASES_PER_RUN` to cap a
   live run; it limits submissions but still persists validation results.

Site configs are operational inputs. Keep credentials in protected environment
files rather than committing them to a site config.

### Cron Setup

1. Copy `sites/crontab.example` outside the repository.
2. Set the deployment's `SIMBOARD_ROOT`.
3. Create and populate the protected Chrysalis environment file with
   `make chrysalis-init-environment`; it must export the API URL and token.
4. Set `SIMBOARD_ENV_FILE` in the cron environment only to override the
   Chrysalis default, such as for a production-targeting job.
5. Install the adjusted copy with `crontab`.

The example schedules staging scans every 15 minutes and archive scans daily at
12:00 UTC. Never place token values in the repository or crontab.

## NERSC Diagnostics Link Scanner

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

- `MACHINE_NAME` (required; `perlmutter` for this wrapper)
- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`

`SIMBOARD_API_BASE_URL` defaults to the development API URL in the wrapper, but
set it explicitly for non-development runs. The scanner reads the reviewed
static registry rather than archive scan-mode or archive-root settings.

## One-Time Chrysalis E3SM v3 Archive Backfill

`v3_data/lcrc_v3_archive_ingestor.py` is a targeted remote-upload backfill for
simulations stored on LCRC Chrysalis and listed in
the [E3SM v3 simulation table](https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/CoupledSystem/simulation_data/simulation_table.html).
It uses a static copy of the table's `Simulation` values, matches archive case
directory leaf names exactly, forces archive scanning from `2024-01`, and
reuses the HPC upload runner's discovery, validation, deduplication, packaging,
and `/api/v1/ingestions/from-hpc-upload` request logic.

### Configure

Copy the committed template outside the repository, secure it, and replace its
placeholders:

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

### Run from the Repository Root

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

### Fixed and Supported Settings

The source site and scan scope are fixed. The runner ignores:

- `SCAN_MODE`
- `ARCHIVE_YEAR_START`
- `MACHINE_NAME`

The following controls remain supported:

- `MAX_ATTEMPTS`
- `MAX_CASES_PER_RUN`
- `REQUEST_TIMEOUT_SECONDS`
- `ARCHIVE_YEAR_END`

### State Behavior

This targeted runner does not read or write database-backed archive snapshot
checkpoints. A filtered backfill cannot safely mark a mixed snapshot as complete
for the general archive runner. Processed-execution state and immutable
discovery results still make repeated runs idempotent.

## E3SM v3 HPSS Linker

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

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker --apply
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```
