# Set Up Ingestion Operations

Use this guide to provision and operate scheduled performance ingestion, the v3
backfill, and diagnostics discovery. Start every new job with `DRY_RUN=true`.

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

| Archive access | Job | Where it runs |
| --- | --- | --- |
| Archive is mounted in the SimBoard backend | Path ingestion | NERSC Spin CronJob |
| Archive is available only at an HPC site | Archive upload | Site scheduler or cron |

Use path ingestion for Perlmutter data mounted in NERSC Spin. Use archive upload for Chrysalis and other remote sites. Create the service account and token first: [HPC API Token Authentication](hpc-api-token-authentication.md).

## Remote-site operations

### Define the deployment root

`SIMBOARD_ROOT` is the deployment root for the remote scheduler. Provisioning
clones the current `main` branch of the canonical SimBoard repository beneath
this root; use `SIMBOARD_REPOSITORY_URL` or `SIMBOARD_REPOSITORY_REF` only when
an approved deployment requires a different source, branch, or tag.

| Machine | `SIMBOARD_ROOT` | Site config | Repository checkout |
| --- | --- | --- | --- |
| Chrysalis | `/lcrc/group/e3sm2/simboard` | `sites/configs/chrysalis.config` | `${SIMBOARD_ROOT}/repository/simboard` |

### Provision the runtime

1. Add a reviewed `backend/app/scripts/ingestion/sites/configs/<site>.config` with the site machine name, staging and archive roots, runner module, and archive lower bound.
2. Export the deployment root. Provisioning creates the root when absent,
   then creates the standardized `operations` workspace and `repository/simboard`; the launcher uses
   `repository/simboard/backend`. For Chrysalis:

   ```bash
   export SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   ```
3. Provision the deployment-local `operations/` workspace and SimBoard checkout:

   ```bash
   make operations-provision
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
`simboard-ingestion-<scan-mode>-<site>-<environment-file>-<UTC timestamp>.log`.
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

### Configure protected API environments

Create the protected API files:

```bash
make operations-init-env site=chrysalis
```

Each command prompts for `SIMBOARD_API_BASE_URL` (with the environment
template's public URL as the default) and the matching `SIMBOARD_API_TOKEN`,
without echoing either token. It creates `operations/env.dev.sh` and
`operations/env.prod.sh` only after all values are supplied.

### Install scheduler configuration

Copy the site crontab into `operations/`, edit its `SIMBOARD_ROOT` and schedules
if needed, then install it:

```bash
make operations-init-cron site=chrysalis
crontab /lcrc/group/e3sm2/simboard/operations/chrysalis.crontab
```

Review `operations/raw_logs/simboard-ingestion-*.log`. After the dry-run
results are correct, uncomment `DRY_RUN=false` in the copied crontab. Use
`MAX_CASES_PER_RUN` for a bounded first live run.

The copied crontab:

- runs `make operations-refresh` (via the deployed refresh helper) weekly to
  refresh a clean checkout;
- synchronizes the backend runtime only after a revision change;
- writes refresh output to `simboard-ingestion-provision.log`; review it after
  each update;
- uses a process lock when `flock` is available; macOS does not include it by
  default, so local refreshes proceed without that lock;
- adds the standard user-level `uv` location to the refresh command's `PATH`;
  adjust it if the scheduler account installs `uv` elsewhere;
- creates staging and archive jobs for both development and production; and
- gives each ingestion command its own `SIMBOARD_ENV_FILE`; development and
  production jobs use separate locks and may run at the same time; staging and
  archive jobs for one environment also use separate locks and may run at the
  same time.

### Reference: configuration files and variables

| Location | Configure |
| --- | --- |
| `sites/configs/<site>.config` | `SIMBOARD_INGESTOR_MODULE`, `SIMBOARD_DEFAULT_ARCHIVE_YEAR_START`, `PERF_ARCHIVE_ROOT`, `OLD_PERF_ARCHIVE_ROOT`, `MACHINE_NAME` |
| `operations/` | Deployment-local workspace, created with `make operations-provision`; stores protected environment files, locks, the top-level provisioning log, and copied crontabs |
| `operations/raw_logs/` | Per-launcher-run logs; apply the site's retention policy without recording secrets |
| `operations/quality_assurance/` | One-off validation artifacts reviewed by operators, never recurring job output |
| `repository/simboard` | Deployment checkout, cloned and prepared by `make operations-provision`, then updated by `make operations-refresh` |
| `operations/env.dev.sh` | Development `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` |
| `operations/env.prod.sh` | Production `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` |
| Copied crontab | `SIMBOARD_ROOT`; optional `DRY_RUN`, `MAX_CASES_PER_RUN`, `ARCHIVE_YEAR_START`, and `ARCHIVE_YEAR_END` |
| Each cron command | `SIMBOARD_ENV_FILE` pointing to `env.dev.sh` or `env.prod.sh` |

Do not put tokens in the site config or crontab. `DRY_RUN_USE_REMOTE_STATE=false` is available only for a credential-free offline scan.

### Migrate an existing deployment

1. Run `make operations-provision` to add `raw_logs/` and
   `quality_assurance/` without replacing existing deployment-local files.
2. Update the copied crontab with `make operations-init-cron` only after
   preserving and manually updating its schedules and `SIMBOARD_ROOT`, or edit
   the existing copied crontab to use the new provisioning-log path.
3. Let existing `SBCS-*` lock files remain until no scheduler invocation uses
   the previous launcher or refresh helper. New helpers acquire an existing
   legacy lock as a compatibility guard, so they do not overlap a running old
   helper.
4. New launcher logs are written only to `raw_logs/`; retain or remove old
   top-level `SBCS-*.log` files according to the site's retention policy after
   confirming the updated crontab is active.

## NERSC Spin operations

Use NERSC Spin path ingestion when the performance archive is mounted in the
backend deployment. It does not use the remote-site launcher or scheduler
configuration above. Follow the [NERSC Spin Ingestion Operations Runbook](nersc-spin-runbook.md) to
configure its staging and archive CronJobs, secrets, and dry-run controls.

## E3SM v3 metadata backfill operation

This one-time Chrysalis job scans the fixed v3 case list from the fixed archive lower bound. It does not update general archive checkpoints.

1. Create the protected v3 configuration in the deployment operations workspace:

   ```bash
   make operations-init-v3-env \
     SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
     environment=prod
   ```

   The command prompts for the API endpoint and token, then creates
   `${SIMBOARD_ROOT}/operations/lcrc-v3.prod.env` with protected permissions.
   The committed `lcrc-v3.env.example` supplies the diagnostics-source default
   and documents optional archive-root overrides.

2. Run and review the dry run:

   ```bash
   make v3-ingest-dry-run \
     SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
     environment=prod
   ```

3. Resolve any `v3_case_missing` or transient errors, then run:

   ```bash
   make v3-ingest-apply \
     SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
     environment=prod
   ```

The same configuration supports v3 diagnostics backfill:

```bash
make v3-diagnostics-dry-run \
  SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
  environment=prod
```

For a nonstandard secure location, pass `V3_ENV_FILE=/path/to/v3.env` in
addition to `SIMBOARD_ROOT` and `environment`. Optional variables in the v3
file are `OLD_PERF_ARCHIVE_ROOT`, `MAX_ATTEMPTS`, `MAX_CASES_PER_RUN`,
`REQUEST_TIMEOUT_SECONDS`, and `ARCHIVE_YEAR_END`.

## Diagnostics discovery operation

Diagnostics discovery is separate from performance ingestion and links published zppy output to an existing SimBoard case.

1. Configure and publish zppy output as described in [Configure zppy Diagnostics for SimBoard](../user/diagnostics.md).
2. Add the machine's filesystem root and public URL to the reviewed registry in `backend/app/scripts/ingestion/diagnostics_archives.py`.
3. Run a dry scan from the backend directory:

   ```bash
   MACHINE_NAME=perlmutter DRY_RUN=true \
     uv run python -m app.scripts.ingestion.diagnostics_link_scanner
   ```

4. For a live scan, set `DRY_RUN=false` and provide `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` in the scheduler environment.

| Configure in | Variables |
| --- | --- |
| Scheduler environment | `MACHINE_NAME`, `DRY_RUN` |
| Live-scan scheduler secret | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` |

## Operate safely

- Review dry-run logs before enabling a live job.
- A successful validation is not an ingestion; only a successful request records an execution as processed.
- Correct filesystem or network failures and let the next scheduled run retry them.
- Keep tokens out of logs, source control, site configs, and crontabs.
