# Set Up Ingestion Operations

## Logging

Ingestion defaults to INFO. Set `SIMBOARD_INGESTION_LOG_LEVEL=DEBUG` in the
scheduler environment or invocation for per-execution decisions and progress.
Use INFO or DEBUG when collecting aggregate run metrics; higher severity
thresholds suppress those records. The launcher captures early failures in
`operations/raw_logs` when writable; retain scheduler stderr capture when the
deployment root or log directory is unavailable. See the
[logging contract](../architecture/ingestion-logging.md) for categories,
count definitions, and the canonical JSON record.

Use this guide to provision and operate scheduled performance ingestion, the v3
backfill, and diagnostics discovery. Start new ingestion jobs with `DRY_RUN=true`;
scheduled diagnostics jobs are configured for live linking.

## Prerequisites

Before provisioning remote-site operations, complete these validations in order:

1. Follow [Test Ingestion Operations](test-ingestion-operations.md) to verify
   the provisioning, protected-environment, cron-generation, and refresh
   workflows in an isolated test deployment.
2. On the target HPC site, verify the reviewed site configuration, scheduler
   account, required modules, archive paths, and API connectivity with a dry
   run before installing or enabling a scheduled live job.

The isolated test validates the shared operations workflow but does not validate
site-specific filesystem, scheduler, module, or network configuration.

## Choose an operation

| Archive access                             | Job            | Where it runs          |
| ------------------------------------------ | -------------- | ---------------------- |
| Archive is mounted in the SimBoard backend | Path ingestion | NERSC Spin CronJob     |
| Archive is available only at an HPC site   | Archive upload | Site scheduler or cron |

Use path ingestion for Perlmutter data mounted in NERSC Spin. Use archive upload for Chrysalis and other remote sites. Create the service account and token first: [HPC API Token Authentication](hpc-api-token-authentication.md).

## Remote-site operations

### Define the deployment root

`SIMBOARD_ROOT` is the deployment root for the remote scheduler. Provisioning
clones the current `main` branch of the canonical SimBoard repository beneath
this root; use `SIMBOARD_REPOSITORY_URL` or `SIMBOARD_REPOSITORY_REF` only when
an approved deployment requires a different source, branch, or tag.

| Machine   | `SIMBOARD_ROOT`             | Site config                      | Repository checkout                    |
| --------- | --------------------------- | -------------------------------- | -------------------------------------- |
| Chrysalis | `/lcrc/group/e3sm/simboard` | `sites/configs/chrysalis.config` | `${SIMBOARD_ROOT}/repository/simboard` |

The operator's user account owns scheduling for this deployment.

### Provision the runtime

1. Add a reviewed `backend/app/scripts/ingestion/sites/configs/<site>.config` with the site machine name, staging and archive roots, runner module, and archive lower bound.
2. Export the deployment root. Provisioning creates the root when absent,
   then creates the standardized `operations` workspace and `repository/simboard`; the launcher uses
   `repository/simboard/backend`. For Chrysalis:

   ```bash
   export SIMBOARD_ROOT=/lcrc/group/e3sm/simboard
   ```

3. Provision the deployment-local `operations/` workspace and SimBoard checkout:

   ```bash
   make ops-provision
   ```

This creates `operations/` with restrictive permissions when absent, clones
the latest `main` checkout into `repository/simboard`, and runs
`backend-install` in that checkout. It is safe to rerun: it preserves an
existing `operations/` directory and updates a clean checkout to the selected
remote revision.

#### Operations workspace contract

The scheduler account owns the deployment root and its operations artifacts.
Grant access only to the operational group that needs to run or review the
jobs; provisioning creates its directories with mode `750`, and generated API
environment and crontab files use mode `640`. When the host defines a
`simboard` group and the provisioning account can assign it, provisioning sets
that group and the setgid bit on the operations directories so new artifacts
inherit the shared group. If the account cannot apply the group or permissions,
provisioning emits a warning and continues; the affected directory retains its
existing ownership and permissions.

```text
${SIMBOARD_ROOT}/operations/
├── raw_logs/                         # per-launcher-run output
├── quality_assurance/                # one-off, operator-reviewed artifacts
├── env.dev.sh
├── env.prod.sh
├── simboard-ingestion-provision.lock
├── simboard-ingestion-provision.log
└── <site>.crontab
```

`raw_logs/` receives files named
`simboard-ingestion-<scan-mode>-<site>-<environment-file>-<UTC timestamp>-<PID>.log`.
The timestamp uses `YYYYMMDD_HHMMSS`; the final suffix is the launcher's Bash
process ID, which distinguishes invocations starting in the same second.
Environment locks are named
`simboard-ingestion-<scan-mode>-<site>-<environment-file>.lock`; this keeps
development and production jobs independent and allows staging and archive jobs
to run concurrently. Repeated runs of the same mode use the same lock.
`quality_assurance/` is not for recurring job output. Do not create
`summarized_logs/` until an approved summary workflow produces and retains
summaries.

Review and retain raw logs according to the site's operational policy, then
remove them with an operator-managed maintenance job. Never log tokens or copy
environment files into `raw_logs/`, `quality_assurance/`, or source control.

The local workflow validation is required before this deployment; see
[Prerequisites](#prerequisites).

### Configure named-operator access (optional)

Use ACLs (Access Control Lists) to share `operations/` with named operators
without creating a `simboard` group. The site must support Linux POSIX ACLs and
permit their use; `getfacl` and `setfacl` must be installed.

Run as the owner of `SIMBOARD_ROOT` and all operations entries. Stop scheduled
jobs and let active jobs finish, then preview and apply:

```bash
make ops-configure-access site=chrysalis operators="ac.tvo ac.bartoletti1"
make ops-configure-access site=chrysalis operators="ac.tvo ac.bartoletti1" apply=true
getfacl "${SIMBOARD_ROOT}/operations" "${SIMBOARD_ROOT}/operations/env.dev.sh"
```

The target:

- grants owner and operators read/write access throughout `operations/`,
  including credentials, logs, and locks, while preserving file execution;
- removes access for unlisted users and groups;
- updates existing entries and sets directory defaults for new entries;
- grants traversal on `SIMBOARD_ROOT`, leaving repository permissions unchanged.

Verify access from operator accounts and rejection from an unlisted account.
SimBoard's creation helpers preserve configured access; external tools and later
`chmod` commands can restrict inherited permissions. Use `getfacl`, not group
mode bits alone, to check effective access.

The ACL marker records the configured directory defaults, including named
operators. Creation helpers fail if those defaults drift; re-run the preview and
apply steps to repair them. Deployments with an older empty marker must also
reapply ACL setup before creating artifacts with the updated helpers.

Keep one scheduler account to limit mixed ownership. Another operator's files
require coordination with their owner or admins before reconfiguring ACLs or
restoring a backup. Review parent permissions separately: operators need
traversal, and broad parent write access can permit renaming or removal.
Repository group-write access remains a trust decision because modified code
can access scheduler credentials.

The helper prints a protected ACL backup and restore command. Changes are not
atomic; restore after a partial failure before retrying. For a first-time setup,
also remove `operations/.simboard-acl-enabled` after restoring. Restoration does
not remove files created after the backup.
For an existing ACL deployment, restoration does not restore marker contents;
reapply the desired operator list before resuming artifact creation.

### Configure protected API environments

Create the protected API files:

```bash
make ops-init-env site=chrysalis
```

Each command prompts for `SIMBOARD_API_BASE_URL` (with the environment
template's public URL as the default) and the matching `SIMBOARD_API_TOKEN`,
without echoing either token. It creates `operations/env.dev.sh` and
`operations/env.prod.sh` only after all values are supplied.

### Install scheduler configuration

Copy the site crontab into `operations/`:

```bash
make ops-init-cron site=chrysalis
```

Before installing, save the current account's crontab in a protected location
and merge unrelated entries into the reviewed file: `crontab <file>` replaces
the entire account's crontab. Set the copied file's `SIMBOARD_ROOT` to
`/lcrc/group/e3sm/simboard` and review its dev/prod environment selections.
Leave `DRY_RUN=false` commented during validation: diagnostics runs offline and
log archiving only previews actions.

After reviewing the merged file, install it:

```bash
crontab /lcrc/group/e3sm/simboard/operations/chrysalis.crontab
```

After offline diagnostics discovery succeeds, enable the reviewed diagnostics
entries and reinstall the file with the `crontab` command above. Leave the global
run-mode setting commented to keep diagnostics offline and ingestion in dry-run
mode. Supply approved API credentials before enabling live linking.

Review `operations/raw_logs/simboard-ingestion-*.log` and diagnostics logs. After
both workflows pass validation and live ingestion and linking are approved,
preview log archiving, then uncomment global `DRY_RUN=false` to enable submissions,
linking, and verified raw-log deletion. Reinstall the reviewed file; use per-job
`DRY_RUN=true` overrides for tasks not yet approved. Use `MAX_CASES_PER_RUN` to
bound the first live ingestion run; it does not limit diagnostics.

After installation, verify `crontab -l` matches the reviewed schedules and new
root, retains unrelated entries, and has no obsolete duplicate jobs in the
operator's account. Review the first scheduled-run logs before declaring the
deployment complete.

The copied crontab:

- runs `make ops-refresh` (via the deployed refresh helper) weekly to
  refresh a clean checkout;
- synchronizes the backend runtime only after a revision change;
- writes refresh output to `simboard-ingestion-provision.log`; review it after
  each update;
- uses a process lock when `flock` is available; macOS does not include it by
  default, so local refreshes proceed without that lock;
- adds the standard user-level `uv` location to the refresh command's `PATH`;
  adjust it if the scheduler account installs `uv` elsewhere;
- creates staging, archive, and independent diagnostics jobs for both development and production;
- gives each ingestion command its own `SIMBOARD_ENV_FILE`; development and
  production jobs use separate locks and may run at the same time; staging and
  archive jobs for one environment also use separate locks and may run at the
  same time; and
- runs diagnostics every six hours at 02:00, 08:00, 14:00, and 20:00 UTC
  with separate locks and the shared top-level run mode;
- archives completed launcher logs weekly on Sunday at 01:00 UTC, using the
  deployment's backend Python and shared `DRY_RUN` setting.

### Weekly launcher-log archiving

`sites/operations/archive_ingestion_logs.py` archives `operations/raw_logs/` into
Sunday–Saturday UTC `YYYYMMDD-YYYYMMDD.tar.gz` files in `operations/history_logs/`.
Run `make ops-provision` to create both directories with the correct access policy.

- **Retention:** `LOG_RETENTION_DAYS=7` by default; override with a nonnegative
  integer in cron. Weeks qualify only after their end passes the retention cutoff.
  Weekly scheduling normally retains 7–14 days of raw logs; zero still excludes
  the current week.
- **Eligibility:** Recognized launcher logs must end with
  `event=launcher_finished exit_code=...`, including failed runs. Incomplete,
  invalid, legacy, unrelated, and symlink inputs remain untouched for manual review.
- **Safety:** Live runs lock, verify, and atomically publish each archive before
  deleting unchanged sources. Identical members are not duplicated; conflicts
  preserve sources and stop the run. Allow space for both old and new archives.
- **Mode:** Unset or true `DRY_RUN` previews only. Set `DRY_RUN=false` to apply;
  `--dry-run` always forces a read-only preview. No API credentials are needed.

Preview from any directory:

```bash
export SIMBOARD_ROOT=/lcrc/group/e3sm/simboard
"${SIMBOARD_ROOT}/repository/simboard/backend/.venv/bin/python" \
  "${SIMBOARD_ROOT}/repository/simboard/backend/app/scripts/ingestion/sites/operations/archive_ingestion_logs.py" \
  --dry-run
```

To apply, remove `--dry-run` and set `DRY_RUN=false`. For isolated tests, pass
`--source-dir` and `--archive-dir`; both are required without `SIMBOARD_ROOT`.

Review `operations/simboard-log-archiving.log` after each run. Errors stop later
weeks; resolve the error, preview, and retry. Failed publication preserves existing
archives and sources; retries safely handle interrupted cleanup. Never remove the
lock file to bypass a running job. Remove leftover hidden `.tmp` files only after
confirming no archiver is running, and avoid overlapping repository refreshes.

Use `tar -tzf <archive>` to inspect members without extracting into `raw_logs/`.
Archives do not expire automatically. API summarization is a separate task.

### Reference: configuration files and variables

| Location                        | Configure                                                                                                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sites/configs/<site>.config`   | `SIMBOARD_INGESTOR_MODULE`, `SIMBOARD_DEFAULT_ARCHIVE_YEAR_START`, `PERF_ARCHIVE_ROOT`, `OLD_PERF_ARCHIVE_ROOT`, `MACHINE_NAME`                                      |
| `operations/`                   | Deployment-local workspace, created with `make ops-provision`; stores protected environment files, locks, the top-level provisioning log, and copied crontabs |
| `operations/raw_logs/`          | Per-launcher-run logs; apply the site's retention policy without recording secrets                                                                                   |
| `operations/history_logs/`      | Verified weekly launcher-log archives and the archiver's process lock |
| `operations/quality_assurance/` | One-off validation artifacts reviewed by operators, never recurring job output                                                                                       |
| `repository/simboard`           | Deployment checkout, cloned and prepared by `make ops-provision`, then updated by `make ops-refresh`                                                   |
| `operations/env.dev.sh`         | Development `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`                                                                                                         |
| `operations/env.prod.sh`        | Production `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`                                                                                                          |
| Copied crontab                  | `SIMBOARD_ROOT`; optional `DRY_RUN`, `LOG_RETENTION_DAYS`, `MAX_CASES_PER_RUN`, `ARCHIVE_YEAR_START`, and `ARCHIVE_YEAR_END`                                                               |
| Each cron command               | `SIMBOARD_ENV_FILE` pointing to `env.dev.sh` or `env.prod.sh`                                                                                                        |

Do not put tokens in the site config or crontab. `DRY_RUN_USE_REMOTE_STATE=false` is available only for a credential-free offline scan.

Site configuration owns the filesystem roots and machine identity for the
general-purpose ingestors. They have no fallback paths or machine name: staging
requires `PERF_ARCHIVE_ROOT`, archive requires `OLD_PERF_ARCHIVE_ROOT`, and both require
`MACHINE_NAME`. Unset or blank required values are configuration errors. Site
files may supply overridable site-specific values; direct Python invocations
must receive explicit deployment values.

The targeted Chrysalis v3 runner is site-specific: it supplies the machine
identity `chrysalis` and the default archive root
`/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF` before shared validation, so its
protected environment file does not need `MACHINE_NAME` or
`OLD_PERF_ARCHIVE_ROOT`. Set an explicit nonblank `OLD_PERF_ARCHIVE_ROOT` to
override the v3 archive path.

Routine archive scans across sites default `ARCHIVE_YEAR_START` to `2025-01`
when unset or blank, with no default upper bound. Set an explicit earlier bound
for an intentional historical backfill. The targeted Chrysalis v3 operation
retains its fixed `2024-01` lower bound.

### Migrate an existing deployment

Before rolling out ingestion configuration changes, review protected environment
files, copied crontabs, and Spin secrets for explicit archive bounds that override
the routine default. Confirm the active filesystem root and `MACHINE_NAME` are
configured for general-purpose ingestors, especially for direct Python
invocations. The targeted v3 runner supplies these site values itself as
described above. Validate with a dry run
before enabling live ingestion; do not reuse NERSC host paths inside Spin.

1. Run `make ops-provision` to add `raw_logs/`, `history_logs/`, and
   `quality_assurance/` without replacing existing deployment-local files.
2. Update the copied crontab with `make ops-init-cron` only after
   backing up the existing file; the initializer refuses to overwrite it.
   Alternatively, merge the template's diagnostics, log-archiving, and
   provisioning-log changes, preserving local schedules and `SIMBOARD_ROOT`. Diagnostics
   entries enable live linking, so confirm API credentials before installation.
3. Let existing `SBCS-*` lock files remain until no scheduler invocation uses
   the previous launcher or refresh helper. New helpers acquire an existing
   legacy lock as a compatibility guard, so they do not overlap a running old
   helper.
4. New launcher logs are written only to `raw_logs/`; retain or remove old
   top-level `SBCS-*.log` files according to the site's retention policy after
   confirming the updated crontab is active.
5. Merge the weekly archiving entry and preview before enabling live mode.
   Remove old `log_redux.py` jobs; logs in `history_logs/deleted/` need manual
   review, not an assumption that they were archived.

### Manual machine-based ingestion

Run commands from the repository root. This is useful for quicker testing and debugging.
Review the dry-run results before running `ingest-apply`.
Both targets require `scan_mode=archive` or `scan_mode=staging`; there is no default.

#### Chrysalis

After provisioning Chrysalis:

```bash
make ingest-dry-run machine=chrysalis SIMBOARD_ROOT=/lcrc/group/e3sm/simboard env=dev scan_mode=archive
make ingest-apply machine=chrysalis SIMBOARD_ROOT=/lcrc/group/e3sm/simboard env=dev scan_mode=archive MAX_CASES_PER_RUN=5
```

- **Environment:** Use `env=prod` for production. Targets load `$SIMBOARD_ROOT/operations/env.<env>.sh`; use `env_file=/path/to/protected.env` to override it.
- **Execution:** Uses `chrysalis.config` and the HPC upload ingestor through the existing launcher, preserving its runtime, file logs, and locks.
- **Output:** Both Make targets print the log path and stream launcher and ingestor output to the terminal while retaining the per-run log in `$SIMBOARD_ROOT/operations/raw_logs/`. Scheduled launcher invocations remain file-only by default; set `SIMBOARD_CONSOLE_LOG=true` to also stream their output. Lock contention is reported even when a staging run exits successfully without starting ingestion.

#### Perlmutter / NERSC

For NERSC path ingestion:

```bash
make ingest-dry-run machine=perlmutter env=dev scan_mode=archive env_file=/path/to/protected.env
make ingest-apply machine=perlmutter env=dev scan_mode=archive env_file=/path/to/protected.env MAX_CASES_PER_RUN=5
```

- **Environment:** Loads API settings from `env_file`, or uses exported settings if omitted. **`env` alone does not switch credentials.**
- **Execution:** Uses `perlmutter.config` and the NERSC archive ingestor with the current checkout’s backend Python. Override Python with `PYTHON_BIN`; `SIMBOARD_ROOT` is not required.
- **Output and locking:** Output goes to the terminal or scheduler. This path adds no launcher file logs or locks. **Avoid overlap with scheduled NERSC jobs.**

## NERSC Spin operations

Use NERSC Spin path ingestion when the performance archive is mounted in the
backend deployment. It does not use the remote-site launcher or scheduler
configuration above. Follow the [NERSC Spin Ingestion Operations Runbook](nersc-spin-runbook.md) to
configure its staging and archive CronJobs, secrets, and dry-run controls.

## E3SM v3 metadata backfill operation

This one-time Chrysalis job scans the fixed v3 case list from the fixed archive lower bound. It does not update general archive checkpoints.

1. Create the protected v3 configuration in the deployment operations workspace:

   ```bash
   make ops-init-v3-env \
     SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
     env=prod
   ```

   The command prompts for the API endpoint and token, then creates
   `${SIMBOARD_ROOT}/operations/lcrc-v3.prod.env` with protected permissions.
   The committed `lcrc-v3.env.example` supplies the diagnostics-source default
   and documents optional archive-root overrides.

2. Run and review the dry run:

   ```bash
   make v3-ingest-dry-run \
     SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
     env=prod
   ```

3. Resolve any `v3_case_missing` or transient errors, then run:

   ```bash
   make v3-ingest-apply \
     SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
     env=prod
   ```

The same configuration supports v3 diagnostics backfill:

```bash
make v3-diags-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
  env=prod
```

To retry one case without comparing or scanning the other cases, specify
its exact reviewed name. First review the dry-run reconciliation, then apply:

```bash
make v3-diags-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
  env=prod case_name=v3.LR.historical_0201

make v3-diags-apply \
  SIMBOARD_ROOT=/lcrc/group/e3sm/simboard \
  env=prod case_name=v3.LR.historical_0201
```

Omit `case_name` to process every mapped case for the machine. The filter
does not bypass existing-copy verification or overwrite conflicting files.

For a nonstandard secure location, pass `env_file=/path/to/v3.env` in
addition to `SIMBOARD_ROOT` and `env`. Optional variables in the v3
file are `OLD_PERF_ARCHIVE_ROOT`, `MAX_ATTEMPTS`, `MAX_CASES_PER_RUN`,
`REQUEST_TIMEOUT_SECONDS`, and `ARCHIVE_YEAR_END`.

## Diagnostics linking

Discovery logs tier start/completion events and throttled progress roughly every
30 seconds during directory traversal and candidate validation. Progress includes
the tier, phase, elapsed seconds, directories visited, provenance files found,
cases checked, and valid candidates. Filesystem calls can block between events;
these logs are not guaranteed heartbeats. Set `SIMBOARD_CONSOLE_LOG=true` for
interactive diagnostics Make targets to stream the retained log to the console.

The scanner links published zppy diagnostics to existing SimBoard cases. Publish
output using [Configure zppy Diagnostics for SimBoard](../user/diagnostics.md)
and verify the machine's archive in `backend/app/scripts/ingestion/diagnostics_archives.py`.

### Scheduled scans on Chrysalis

1. Confirm the scheduler account can read the diagnostics archive and the
   protected API files contain authorized service-account credentials.
2. Merge the template's dev/prod diagnostics entries into the installed crontab.
   They run at 02:00, 08:00, 14:00, and 20:00 UTC with separate locks and inherit
   global `DRY_RUN`. Leave it unset or `true` for offline scans; set it to `false`
   only after approving live ingestion and diagnostics linking, or use per-job
   overrides when approvals differ.
3. To run a scan manually, run Make from the deployed repository root
   (`${SIMBOARD_ROOT}/repository/simboard`) and select the API environment explicitly:

   ```bash
   make diags-dry-run SIMBOARD_ROOT="${SIMBOARD_ROOT}" site=chrysalis env=prod
   make diags-apply SIMBOARD_ROOT="${SIMBOARD_ROOT}" site=chrysalis env=prod
   ```

   Use `env=dev` for development. The dry-run target scans offline without loading
   API credentials; `env` selects log and lock naming. The apply target loads the
   protected `operations/env.<env>.sh` file and enables live linking. Both targets
   use the existing launcher for locks, logs, and exit status. These targets only
   link already-published output; use `v3-diags-*` for historical backfill.
   Dry-run and apply share the selected environment's diagnostics lock with
   scheduled scans. A concurrent run fails without starting the scanner; check
   the indicated log location for lock contention or scanner failures.

4. Review `operations/raw_logs/simboard-diagnostics-chrysalis-*.log` and verify
   links in SimBoard. Each scan walks the full archive; ingestion year/case limits
   do not apply.

### Scheduled scans on NERSC Spin

Configure a separate CronJob through Rancher using the
[NERSC Spin runbook](nersc-spin-runbook.md#workload-4-nersc-diagnostics-scanner-cronjob).

### Check scanner results

- `diagnostics_scanner_startup_configuration` reports the machine, archive and run mode.
- `diagnostics_scanner_completed` reports the outcome and counters collected so far.
- Fatal errors log `diagnostics_scanner_failed` and exit nonzero. Discovery failures
  may leave the candidate count at zero; abrupt termination may omit the summary.
- Nonzero `deferred_state_lookups` or `failed_link_submissions` also cause a
  nonzero exit and a failed summary outcome. Later scans retry deferred work and
  skip unchanged links.

## Operate safely

- Review ingestion dry-run logs before enabling live ingestion. Diagnostics dry
  runs are optional; review live diagnostics counters and links after deployment.
- A successful validation is not an ingestion; only a successful request records an execution as processed.
- Correct filesystem or network failures and let the next scheduled run retry them.
- Keep tokens out of logs, source control, site configs, and crontabs.
