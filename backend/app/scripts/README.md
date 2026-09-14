# Operational Scripts

This directory contains internal operational entry points. This page covers
ingestion and diagnostics; use `make help` for database-management and
account-provisioning commands. Run Python scripts as modules from the backend
project root:

```bash
uv run python -m app.scripts.ingestion.nersc_archive_ingestor
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
uv run python -m app.scripts.ingestion.diagnostics_link_scanner
```

Do not execute Python scripts directly by file path; module execution preserves
package imports and application configuration.

## Ingestion Operations

The step-by-step setup, site configuration, cron, environment-variable, targeted
E3SM v3 backfill, and diagnostics instructions are maintained in
[Set Up Ingestion Operations](../../../docs/operations/setup-ingestion-operations.md).

Use the runner selected by archive access:

| Archive location | Runner |
| --- | --- |
| Mounted in the SimBoard backend environment | `nersc_archive_ingestor.py` |
| Available only at a remote HPC site | `hpc_upload_archive_ingestor.py` via `sites/site_ingestion_launcher.sh` |

For service-account and API-token provisioning, see
[HPC API Token Authentication](../../../docs/operations/hpc-api-token-authentication.md).

```bash
app/scripts/ingestion/sites/site_ingestion_launcher.sh nersc staging
app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis archive
```

Each site config defines its machine name, archive roots, Python environment
file, token export file, API base URL, archive lower bound, and ingestor module.
Set `SIMBOARD_ROOT` to a shared operational directory containing
`repository/simboard` and `operations`; the launcher derives the backend and
working paths from it. A site config may instead set `SIMBOARD_MODULES` and
`SIMBOARD_WORKDIR` explicitly before using either variable. The launcher defaults to `DRY_RUN=true` with
`DRY_RUN_USE_REMOTE_STATE=true`, so it loads API credentials and performs
read-only state validation. Set `DRY_RUN_USE_REMOTE_STATE=false` for a
credential-free offline scan. Set `DRY_RUN=false` only after validating archive
access, token storage, network egress, and candidate counts. A capped
`MAX_CASES_PER_RUN` value limits real ingestion but still persists results.

Site configs are operational inputs. Keep credentials in their referenced,
protected files rather than committing them to a config file.

### Cron Setup

Copy `sites/crontab.example` outside the repository, set `SIMBOARD_ROOT` to the
shared operational directory, and install the adjusted file with `crontab`.
The example schedules staging scans every 15 minutes and archive scans daily at
12:00 UTC. The token file referenced by the site config must be readable only by
the account that runs the scheduled job and export `SIMBOARD_API_TOKEN` when
sourced. Keep token values out of the repository and crontab.

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
Each case ingested by this workflow is classified as `production`; diagnostics
backfill workflows do not set case classifications.

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

It also supplies `V3_DIAGNOSTICS_SOURCE_ROOT` to the diagnostics backfill. The
template defaults this to the Chrysalis diagnostic-output root; override it
only when that directory is mounted elsewhere.

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

#### Backfill v3 Diagnostics

Use the same `lcrc-v3.env` file for diagnostics. Start with reconciliation-only
mode, which does not copy diagnostics, generate settings, or run the scanner:

```bash
make v3-diagnostics-dry-run LCRC_V3_ENV_FILE=~/.config/simboard/lcrc-v3.env
```

After reviewing the reconciliation event, run the explicit write-enabled
backfill and scanner linkage:

```bash
make v3-diagnostics-apply LCRC_V3_ENV_FILE=~/.config/simboard/lcrc-v3.env
```

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

```bash
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker --apply
python -m app.scripts.ingestion.v3_data.lcrc_v3_hpss_linker
```
