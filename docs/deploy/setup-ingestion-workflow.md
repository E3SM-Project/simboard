# Set Up an Ingestion Workflow

Use this guide to configure scheduled performance-metadata ingestion, the targeted E3SM v3 backfill, and diagnostics-link discovery. Start with a dry run. A dry run with remote state enabled requires the API credentials but does not change SimBoard data.

## 1. Choose the performance workflow

| Where the performance archive is readable | Workflow | Runner |
| --- | --- | --- |
| In the SimBoard backend environment | Local path submission | `nersc_archive_ingestor` |
| Only on the HPC site | Remote archive upload | `hpc_upload_archive_ingestor` through the site launcher |

Use local path submission for Perlmutter archives mounted into the NERSC Spin backend. Use remote archive upload for Chrysalis and other sites whose archives are not mounted in Spin. Each remote request contains one case archive.

Before configuring either workflow, create a SimBoard service account and token with the instructions in [HPC API Token Authentication](hpc-api-token-authentication.md). The token must be available only to the scheduler account or authorized operations group.

## 2. Configure performance-metadata ingestion

### 2.1 Configure a remote HPC site

This procedure applies to Chrysalis and to a new remote site after a reviewed site configuration has been added under `backend/app/scripts/ingestion/sites/`.

1. On the HPC site, install the repository and create the backend environment with `make install` from the repository root.
2. Create a protected API environment file outside the repository. For Chrysalis, create it with:

   ```bash
   make ingestion-init-env site=chrysalis SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   make ingestion-init-env site=chrysalis environment=prod SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard
   ```

3. `SIMBOARD_ROOT` determines the output location: `operations/env.dev.sh` by default, or `operations/env.prod.sh` with `environment=prod`. Each template supplies its public API URL: `env.dev.sh` uses `https://simboard-dev-api.e3sm.org` and `env.prod.sh` uses `https://simboard-api.e3sm.org`. Add the matching service-account token. Do not put the token in the site configuration or crontab.
4. Confirm the site configuration supplies the machine name and performance roots. The committed Chrysalis configuration is `backend/app/scripts/ingestion/sites/chrysalis.config`. For a new site, add a reviewed `<site>.config` with the site-specific machine name, staging root, archive root, runner module, and archive lower bound.
5. Run a staging dry run from the site operations directory:

   ```bash
   backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis staging
   ```

6. Review the generated `SBCS-*.log` file for discovered candidates, rejected metadata, transient failures, and API-state access.
7. Enable live ingestion only after review by setting `DRY_RUN=false` in the job environment. Set `MAX_CASES_PER_RUN` for the first live run if a bounded rollout is needed.

#### Remote-site environment variables

| Configure in | Variables | Purpose |
| --- | --- | --- |
| Protected API file, normally `/lcrc/group/e3sm2/simboard/operations/env.dev.sh` for Chrysalis | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` | Required for live runs and remote-state dry runs. The token authenticates state, discovery-result, and upload requests. |
| Committed reviewed site file, such as `backend/app/scripts/ingestion/sites/chrysalis.config` | `SIMBOARD_INGESTOR_MODULE`, `SIMBOARD_DEFAULT_ARCHIVE_YEAR_START`, `PERF_ARCHIVE_ROOT`, `OLD_PERF_ARCHIVE_ROOT`, `MACHINE_NAME` | Site-specific runner and archive defaults. Do not store credentials or run controls here. |
| Scheduler or crontab environment | `SIMBOARD_ROOT` | Standard deployment root containing `repository/simboard/backend` and `operations`. |
| Scheduler or crontab environment, only when needed | `SIMBOARD_ENV_FILE`, `SIMBOARD_SITE_CONFIG`, `PYTHON_BIN`, `DRY_RUN`, `DRY_RUN_USE_REMOTE_STATE`, `MAX_CASES_PER_RUN`, `MAX_ATTEMPTS`, `REQUEST_TIMEOUT_SECONDS`, `ARCHIVE_YEAR_START`, `ARCHIVE_YEAR_END` | Per-job API target, selected site configuration, interpreter, execution controls, and archive scope. `DRY_RUN_USE_REMOTE_STATE=false` permits a credential-free offline scan only. |

The launcher sets `SCAN_MODE` from its second argument (`staging` or `archive`). Do not set it separately for launcher jobs.

### 2.2 Configure Perlmutter / NERSC path submission

1. Mount the performance archive into the backend workload at the configured staging and archive roots.
2. Configure the backend workload environment and run `python -m app.scripts.ingestion.nersc_archive_ingestor` from the backend project directory.
3. Start with `DRY_RUN=true`. Review the job log, then set `DRY_RUN=false` for scheduled ingestion.
4. Configure the workload schedule as described in the [NERSC Spin Runbook](nersc-spin-runbook.md). Keep this workflow on its direct Python module command; it does not use the remote-site launcher.

#### NERSC environment variables

| Configure in | Variables | Purpose |
| --- | --- | --- |
| Backend workload secret/environment configuration | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` | API endpoint and service token for live runs and remote-state dry runs. |
| Backend workload environment configuration | `MACHINE_NAME`, `SCAN_MODE`, `PERF_ARCHIVE_ROOT`, `OLD_PERF_ARCHIVE_ROOT`, `DRY_RUN`, `DRY_RUN_USE_REMOTE_STATE` | Source machine, selected mounted root, and dry-run behavior. |
| Backend workload environment configuration, only when needed | `MAX_CASES_PER_RUN`, `MAX_ATTEMPTS`, `REQUEST_TIMEOUT_SECONDS`, `ARCHIVE_YEAR_START`, `ARCHIVE_YEAR_END` | Submission limit, retry/timeout controls, and archive scan scope. |

In archive mode, `ARCHIVE_YEAR_START` and `ARCHIVE_YEAR_END` accept `YYYY` or `YYYY-MM`. Archive scans only process eligible immutable snapshots; completed snapshots are skipped using stored checkpoints.

## 3. Schedule remote-site collection with cron

1. Copy `backend/app/scripts/ingestion/sites/crontab.example` outside the repository.
2. Set `SIMBOARD_ROOT` in that copy so cron can locate the launcher and the launcher can derive its work and backend paths.
3. Replace `chrysalis` with the configured site name, if needed.
4. Set `SIMBOARD_ENV_FILE` immediately before each launcher command. The example includes matching development and production jobs: `env.prod.sh` targets production and `env.dev.sh` targets development. The launcher keeps one lock per environment file, so jobs for different environments can run independently. Keep the staging and archive schedule appropriate for the site. The example runs staging every 15 minutes and archive daily in UTC.
5. Install the copied file with `crontab /path/to/site.crontab`.
6. Confirm that the scheduler account can read the protected API file, the performance roots, and the backend Python interpreter, then review the first `SBCS-*.log` file.

#### Cron environment variables

| Configure in | Variables | Purpose |
| --- | --- | --- |
| Copied crontab | `SHELL`, `PATH`, `CRON_TZ`, `SIMBOARD_ROOT` | Shell, command path, UTC schedule interpretation, and the standard root used to locate the launcher and derive its paths. |
| Each cron command | `SIMBOARD_ENV_FILE` | Selects that job's protected `env.dev.sh` or `env.prod.sh` API file. |
| Copied crontab, only when needed | `ARCHIVE_YEAR_START`, `ARCHIVE_YEAR_END`, `DRY_RUN`, `MAX_CASES_PER_RUN` | Scan controls and bounded rollout. |
| Protected API file referenced by each cron command | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` | Credentials. Never place these values directly in crontab. |

## 4. Run the targeted E3SM v3 metadata backfill

This is a one-time Chrysalis archive workflow. It scans the fixed v3 case list beginning at the fixed `2024-01` archive boundary, uploads matching cases, and does not update general archive snapshot checkpoints.

1. Copy `backend/app/scripts/ingestion/v3_data/lcrc-v3.env.example` to a protected location outside the repository and restrict its permissions.
2. Set its API URL and token.
3. From the repository root, run the dry run:

   ```bash
   make v3-ingest-dry-run LCRC_V3_ENV_FILE=/secure/path/lcrc-v3.env
   ```

4. Review `v3_case_match`, `v3_case_missing`, and `v3_ingestion_summary` events. Resolve missing cases or transient errors before applying.
5. Run the explicit apply command:

   ```bash
   make v3-ingest-apply LCRC_V3_ENV_FILE=/secure/path/lcrc-v3.env
   ```

#### v3 environment variables

| Configure in | Variables | Purpose |
| --- | --- | --- |
| Protected file named by `LCRC_V3_ENV_FILE` | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` | Required API endpoint and service token. |
| Same protected file, only when needed | `OLD_PERF_ARCHIVE_ROOT`, `MAX_ATTEMPTS`, `MAX_CASES_PER_RUN`, `REQUEST_TIMEOUT_SECONDS`, `ARCHIVE_YEAR_END` | Alternate archive root and run controls. |
| Shell or Make invocation | `LCRC_V3_ENV_FILE` | Path to the protected v3 environment file. |

The Make targets set `DRY_RUN`; do not rely on `DRY_RUN` in the v3 environment file to choose dry run versus apply. `SCAN_MODE`, `MACHINE_NAME`, and `ARCHIVE_YEAR_START` are fixed by this workflow.

## 5. Set up diagnostics-link discovery

Diagnostics linking is separate from performance ingestion. It finds published zppy output and adds a link only to an already ingested matching case.

1. Configure zppy output and provenance according to [Configure zppy Diagnostics for SimBoard](../user/diagnostics.md). The published path, case name, machine, and HPC username must match the existing SimBoard case.
2. Verify that the machine is present in the reviewed diagnostics-archive registry at `backend/app/scripts/ingestion/diagnostics_archives.py`. Add a new site there in a reviewed change; the scanner does not accept archive-root or public-URL overrides at runtime.
3. In the scheduler environment, set `MACHINE_NAME` and run the site wrapper with `DRY_RUN=true`:

   ```bash
   MACHINE_NAME=perlmutter DRY_RUN=true \
     backend/app/scripts/ingestion/sites/nersc-diagnostics-scanner.sh
   ```

4. Review discovered candidates. For a live run, export the API URL and token in the scheduler's protected environment, set `DRY_RUN=false`, and run or schedule the same wrapper.

#### Diagnostics environment variables

| Configure in | Variables | Purpose |
| --- | --- | --- |
| Scheduler environment or protected file sourced by the scheduler | `MACHINE_NAME`, `DRY_RUN` | Required source machine and dry-run control. `MACHINE_NAME` must resolve to a reviewed diagnostics archive. |
| Same protected scheduler environment, for live runs | `SIMBOARD_API_BASE_URL`, `SIMBOARD_API_TOKEN` | Required to read scanner state and create links. The wrappers provide a development URL default, but set the URL explicitly outside development. |

The diagnostics scanner has no `SCAN_MODE`, performance-root, or archive-year configuration. It scans only the reviewed diagnostics archive's `production` and `development` tiers. A dry run does not call the API.

## 6. Operate and troubleshoot

- Keep `DRY_RUN=true` for validation; use `MAX_CASES_PER_RUN` to bound a live rollout.
- Treat filesystem and request failures as transient: correct the cause and let the next scheduled run retry them.
- Successful validation is not successful ingestion. Only a successful ingestion records an execution as processed.
- Never commit a token or add it to a site config, crontab, or log command line.
- For API/service-account troubleshooting, use [HPC API Token Authentication](hpc-api-token-authentication.md). For data model and archive behavior, see [Metadata Ingestion Architecture](../architecture/metadata-ingestion.md).
