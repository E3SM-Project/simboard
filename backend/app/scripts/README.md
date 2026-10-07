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

| Archive location                            | Runner                                                                  |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| Mounted in the SimBoard backend environment | `nersc_archive_ingestor.py`                                             |
| Available only at a remote HPC site         | `hpc_upload_archive_ingestor.py` via `sites/site_ingestion_launcher.sh` |

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

### Performance Source Directories

Both runners record observed case and execution directories, including visited
executions that skip uploading. Mappings use metadata identities, retain multiple
staging/archive paths, and appear on the case and execution detail pages.
Mapping failures stop checkpoint completion; rerunning safely retries them.
Dry runs do not write mappings, and checkpointed snapshots remain skipped.
Historical metadata backfill is tracked in GitHub issue #360.

### Cron Setup

Copy `sites/crontab.example` outside the repository, set `SIMBOARD_ROOT` to the
shared operational directory, and install the adjusted file with `crontab`.
The example schedules staging scans every 15 minutes and archive scans daily at
12:00 UTC. The token file referenced by the site config must be readable only by
the account that runs the scheduled job and export `SIMBOARD_API_TOKEN` when
sourced. Keep token values out of the repository and crontab.

## NERSC Diagnostics Link Scanner

### When to Use It

Use the diagnostics scanner to find the newest paired zppy provenance from the
reviewed static registry and create case-scoped diagnostic links. The scanner
does not read Mache configuration at runtime.

### Run It at NERSC

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

## One-Time E3SM Production v3 Case Archive and Diagnostic Backfill

These operations are intended to be run once to backfill existing E3SM v3 production
case archives and diagnostics from Chrysalis.

### 1. v3 Case Archive Backfill

`v3_data/lcrc_v3_archive_ingestor.py` is a targeted remote-upload backfill for
simulations stored on LCRC Chrysalis and listed in
the [E3SM v3 simulation table](https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/CoupledSystem/simulation_data/simulation_table.html).
It uses a static copy of the table's `Simulation` values, matches archive case
directory leaf names exactly, forces archive scanning from `2024-01`, and
reuses the HPC upload runner's discovery, validation, deduplication, packaging,
and `/api/v1/ingestions/from-hpc-upload` request logic.
Each case ingested by this workflow is classified as `production`; diagnostics
backfill workflows do not set case classifications.

For this one-time backfill, create a protected configuration in the deployment
operations workspace. The initializer uses the committed template for defaults
and prompts for the API credentials without echoing the token:

```bash
make operations-init-v3-env \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod
```

This creates `${SIMBOARD_ROOT}/operations/lcrc-v3.prod.env`. It includes
`SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN`, and
`V3_DIAGNOSTICS_SOURCE_ROOT`; override the latter only when the Chrysalis
diagnostic-output directory is mounted elsewhere.

Set `OLD_PERF_ARCHIVE_ROOT` only when the Chrysalis archive is mounted somewhere
other than its documented default.

#### Run from the Repository Root

Start with the Make dry run:

```bash
make v3-ingest-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod
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
make v3-ingest-apply \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod
```

The Make targets override `DRY_RUN`; keep the external environment file focused
on the API credentials and optional archive-root override. They run Python with
unbuffered output so emitted structured events appear in the console immediately.

### 2. v3 Diagnostics Backfill

Use the same v3 configuration for diagnostics. Start with reconciliation-only
mode, which does not copy diagnostics, generate settings, or run the scanner:

```bash
make v3-diagnostics-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod

# Include per-source and aggregate selected-source sizes (may take longer).
make v3-diagnostics-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod \
  include_sizes=true
```

The normal dry run walks **every existing source directory** to compare files.
Large cases can take a long time with no log output between the case-match and
existing-copy-check events. Leaving `include_sizes` unset does not avoid this
comparison.

For a quicker inventory of previously copied cases, opt in to trusting paired
provenance:

```bash
make v3-diagnostics-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=dev \
  trust_existing=true
```

This checks the expected destination for the newest valid `provenance.*.cfg`
and its paired `.settings` (both regular, non-symlink files). It reports
`trusted_existing` **without comparing source files**. It still checks that
the source directory exists, and uses the
normal comparison for destinations without paired provenance. An incomplete
copy or new source files can be missed; use the normal dry run when you need to
verify completeness. The fast mode does not check permissions or links either.

Review `v3_diagnostics_backfill_reconciliation` before applying:

- `skipped_existing`: source paths and file sizes match; the destination has
  paired `.cfg` and `.settings` files.
- `trusted_existing`: paired provenance found in fast mode; contents **not
  compared**.
- `ready_to_repair`: source files are missing from the destination. In this
  case, the dry run has **not yet checked** the provenance pair.
- `provenance_missing`: matching files, but no paired `.cfg` and `.settings`.
- `failed`: inspect conflicts or errors before retrying.

For a one-time rerun of already copied diagnostics, use this checklist:

1. Choose the normal dry run to check existing copies, or the opt-in fast mode
   to inventory them without validating copy completeness.
2. Investigate `ready_to_repair`, `provenance_missing`, `failed`, and other
   unresolved cases. A `.settings` file alone is **not** proof of a complete
   copy. The backfill creates `.settings` after copying, but before updating
   public-read permissions; it can also create a `.cfg` for historic output.
3. Spot-check public-read permissions on archived directories and files.
4. Verify the expected diagnostic links separately (for example, in SimBoard).
   The backfill dry run does **not** run the linkage scanner.

The dry run checks relative paths, file types, and file sizes, **not file
contents or permissions**. It also cannot prove that the source has not changed
since a previous copy. For this one-time job, review exceptions and spot-check
rather than adding a new completion marker.

When you are ready to install missing files and run scanner linkage, use the
explicit write-enabled backfill:

```bash
make v3-diagnostics-apply \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  env=prod
```

The apply target also accepts `trust_existing=true` if you want
to skip source comparisons for paired existing copies **during apply**. It still
includes those cases in the scanner pass. Leave the option unset if you need
the script to detect and repair missing source files.

An existing destination is checked against the source (excluding source
`provenance.*.settings` files) by relative path and file size. This is a
copy-completeness check, not a byte-for-byte integrity check: different
contents with the same size cannot be detected. Missing files are reported as
`ready_to_repair` in the dry run and installed without replacing archive files
during apply (`repaired`). Size or file-type differences are reported as
`failed` for manual review; archive-only files are retained. If a recovered
destination has no paired `.cfg` and `.settings`, it is reported as
`provenance_missing` and the command exits nonzero rather than claiming the
case was linked. Provenance recovery is a separate operation; do not fabricate
a zppy `.cfg` to clear this status.

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

### 3. v3 HPSS Linker

#### Purpose

`v3_data/lcrc_v3_hpss_linker.py` links existing Chrysalis and Perlmutter cases
to the HPSS URLs documented in the E3SM v3 simulation table. It does not ingest
archive data or read the Chrysalis filesystem.

Run it inside the deployed SimBoard backend container or administrative job with:

- `DATABASE_URL` and the normal backend settings
- Network access to the documentation page, unless `--source-file` is used

It does not require `SIMBOARD_API_BASE_URL` or `SIMBOARD_API_TOKEN`.

### Matching and Safety Rules

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

### Dry Run and Apply

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
