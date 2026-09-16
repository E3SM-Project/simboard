# Set Up an Ingestion Workflow

Use this guide for scheduled performance ingestion, the v3 backfill, and diagnostics discovery. Start every new job with `DRY_RUN=true`.

## Choose the performance job

| Archive access | Job | Where it runs |
| --- | --- | --- |
| Archive is mounted in the SimBoard backend | Path ingestion | NERSC Spin CronJob |
| Archive is available only at an HPC site | Archive upload | Site scheduler or cron |

Use path ingestion for Perlmutter data mounted in NERSC Spin. Use archive upload for Chrysalis and other remote sites. Create the service account and token first: [HPC API Token Authentication](hpc-api-token-authentication.md).

## Remote HPC site jobs

### Setup

1. Add a reviewed `backend/app/scripts/ingestion/sites/<site>.config` with the site machine name, staging and archive roots, runner module, and archive lower bound.
2. Set `SIMBOARD_ROOT` to the deployment root. It must contain `operations/` and `repository/simboard/backend/`. For Chrysalis:

   ```bash
   SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   ```
3. Create the protected API files:

   ```bash
   make ingestion-init-env site=chrysalis SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   make ingestion-init-env site=chrysalis environment=prod SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   ```

   These create `operations/env.dev.sh` and `operations/env.prod.sh`. The templates set the public API URL; add the matching service-account token.
4. Copy the site crontab into `operations/`, edit its `SIMBOARD_ROOT` and schedule if needed, then install it:

   ```bash
   make ingestion-init-cron site=chrysalis SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   crontab /lcrc/group/e3sm2/simboard/operations/chrysalis.crontab
   ```
5. Review the `SBCS-*.log` files. After the dry-run results are correct, uncomment `DRY_RUN=false` in the copied crontab. Use `MAX_CASES_PER_RUN` for a bounded first live run.

The cron example creates staging and archive jobs for both development and production. Each command selects its own `SIMBOARD_ENV_FILE`; development and production jobs use separate locks and may run at the same time.

### Configuration files and variables

| Location | Configure |
| --- | --- |
| `sites/<site>.config` | `SIMBOARD_INGESTOR_MODULE`, `SIMBOARD_DEFAULT_ARCHIVE_YEAR_START`, `PERF_ARCHIVE_ROOT`, `OLD_PERF_ARCHIVE_ROOT`, `MACHINE_NAME` |
| `operations/env.dev.sh` | Development `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` |
| `operations/env.prod.sh` | Production `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` |
| Copied crontab | `SIMBOARD_ROOT`; optional `DRY_RUN`, `MAX_CASES_PER_RUN`, `ARCHIVE_YEAR_START`, and `ARCHIVE_YEAR_END` |
| Each cron command | `SIMBOARD_ENV_FILE` pointing to `env.dev.sh` or `env.prod.sh` |

Do not put tokens in the site config or crontab. `DRY_RUN_USE_REMOTE_STATE=false` is available only for a credential-free offline scan.

## NERSC Spin ingestion jobs

Configure these in the backend deployment, not with the remote-site launcher. Follow the [NERSC Spin Runbook](nersc-spin-runbook.md) to create the staging and archive CronJobs.

| Job configuration | Variables |
| --- | --- |
| Secret | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` |
| Staging job | `MACHINE_NAME`, `SCAN_MODE=staging`, `PERF_ARCHIVE_ROOT`, `DRY_RUN` |
| Archive job | `MACHINE_NAME`, `SCAN_MODE=archive`, `OLD_PERF_ARCHIVE_ROOT`, `DRY_RUN`, `ARCHIVE_YEAR_START`, `ARCHIVE_YEAR_END` |
| Optional controls | `DRY_RUN_USE_REMOTE_STATE`, `MAX_CASES_PER_RUN`, `MAX_ATTEMPTS`, `REQUEST_TIMEOUT_SECONDS` |

Keep the CronJob command as `python -m app.scripts.ingestion.nersc_archive_ingestor`.

## E3SM v3 metadata backfill

This one-time Chrysalis job scans the fixed v3 case list from the fixed archive lower bound. It does not update general archive checkpoints.

1. Copy `backend/app/scripts/ingestion/v3_data/lcrc-v3.env.example` to a protected location and set `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`.
2. Run and review the dry run:

   ```bash
   make v3-ingest-dry-run LCRC_V3_ENV_FILE=/secure/path/lcrc-v3.env
   ```

3. Resolve any `v3_case_missing` or transient errors, then run:

   ```bash
   make v3-ingest-apply LCRC_V3_ENV_FILE=/secure/path/lcrc-v3.env
   ```

Optional variables in the same file are `OLD_PERF_ARCHIVE_ROOT`, `MAX_ATTEMPTS`, `MAX_CASES_PER_RUN`, `REQUEST_TIMEOUT_SECONDS`, and `ARCHIVE_YEAR_END`.

## Diagnostics discovery

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

## Normal operation

- Review dry-run logs before enabling a live job.
- A successful validation is not an ingestion; only a successful request records an execution as processed.
- Correct filesystem or network failures and let the next scheduled run retry them.
- Keep tokens out of logs, source control, site configs, and crontabs.
