# Aurora Ingestion

Aurora (ALCF) runs use the same remote-upload path as Chrysalis: a scheduled job
on the HPC side scans the E3SM performance archive and uploads changed cases to
SimBoard over HTTPS. The SimBoard side is in place: the `aurora` machine is
seeded, `aurora.config` selects the upload ingestor, and Make, the launcher, and
the scheduler template all accept `aurora`.

What is not yet decided is site-specific and must be confirmed on Aurora before
anything is scheduled.

## What still has to be confirmed on Aurora

| Item | Why it is open |
| --- | --- |
| Staging root (`PERF_ARCHIVE_ROOT`) | Earlier planning notes list `/lus/flare/projects/E3SM_Dec/performance_archive`, sourced from a PACE reference. Current E3SM machine configuration sets `SAVE_TIMING_DIR` to `/lus/flare/projects/E3SMinput/baselines`, which would place records under `.../E3SMinput/baselines/performance_archive`. These disagree. |
| Archive root (`OLD_PERF_ARCHIVE_ROOT`) | Not recorded anywhere public. |
| Scheduler | Planning notes describe an ALCF GitLab scheduled job; its project, schedule, and runner are not public. |
| Scheduler identity | Which account owns the job, with at least one backup operator. |
| API credentials | A dedicated SimBoard service account for Aurora, stored as a protected GitLab variable or protected file. |
| Network egress | Whether the runner can reach the SimBoard API. |
| Diagnostics | Whether Aurora publishes zppy diagnostics, and where. |

Because the two candidate staging roots disagree, `aurora.config` ships with no
filesystem defaults. A run without explicit roots fails with
`PERF_ARCHIVE_ROOT is required` instead of scanning a guessed location.

Diagnostics scheduling is disabled for Aurora
(`SIMBOARD_DIAGNOSTICS_ENABLED=false`), so `make ops-init-cron site=aurora`
produces staging and archive jobs only. Enable it after adding Aurora to
`backend/app/scripts/ingestion/diagnostics_archives.py` with a verified root and
public URL.

## Validate on Aurora

Use a personal account for this step; it reads the archive and uploads nothing.

1. Inspect the layout and confirm it matches
   `<root>/<user>/<case>/<execution-id>/`, and, for archived snapshots,
   `<root>/YYYY-MM/performance_archive_*/[COMPLETED/]<user>/<case>/<execution-id>/`.

2. Provision a deployment and run an offline dry run:

   ```bash
   make ops-provision SIMBOARD_ROOT=<deployment-root>
   cd <deployment-root>/repository/simboard
   DRY_RUN_USE_REMOTE_STATE=false \
   PERF_ARCHIVE_ROOT=<verified staging root> \
   make ingest-dry-run machine=aurora env=dev scan_mode=staging \
     SIMBOARD_ROOT=<deployment-root>
   ```

   The run summary in `operations/raw_logs/` reports cases found and executions
   accepted, and no requests are made.

3. Pick three executions already visible in PACE and confirm the dry run finds
   each with the same execution ID, case name, and user.

## Enable scheduled ingestion

After validation and an agreed owner:

1. Create the Aurora service account and token (see
   [HPC API Token Authentication](hpc-api-token-authentication.md)), then
   `make ops-init-env site=aurora SIMBOARD_ROOT=<deployment-root>`.
2. Run a dry run with remote state against development.
3. Run a bounded live upload to development and compare the records with PACE:

   ```bash
   PERF_ARCHIVE_ROOT=<verified staging root> \
   make ingest-apply machine=aurora env=dev scan_mode=staging \
     SIMBOARD_ROOT=<deployment-root> MAX_CASES_PER_RUN=5
   ```

4. Schedule the launcher with the verified roots exported in the job
   environment. For cron, `make ops-init-cron site=aurora` renders the schedule.
   For a GitLab schedule, invoke the same command:

   ```bash
   SIMBOARD_ROOT=<deployment-root> \
   SIMBOARD_ENV_FILE=<deployment-root>/operations/env.dev.sh \
   PERF_ARCHIVE_ROOT=<verified staging root> \
   OLD_PERF_ARCHIVE_ROOT=<verified archive root> \
   <deployment-root>/repository/simboard/backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh \
     aurora staging
   ```

   The launcher requires `flock`.

The scan is read-only, so it can run alongside the existing PACE collection
against the same directory.

## Ownership

Schedule the job under a project-owned identity where ALCF provides one. If only
a personal account can own it, keep the deployment in shared project storage,
grant a backup operator access with `make ops-configure-access`, and use a
service-account token rather than personal credentials.
