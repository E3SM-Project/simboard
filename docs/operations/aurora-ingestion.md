# Aurora Ingestion

Aurora (ALCF) runs use the same remote-upload path as Chrysalis: a scheduled job
on the HPC side scans the E3SM performance archive and uploads changed cases to
SimBoard over HTTPS. The SimBoard side is in place: the `aurora` machine is
seeded, `aurora.config` selects the upload ingestor, and Make, the launcher, and
the scheduler template all accept `aurora`.

## How PACE lays out Aurora's archive

PACE's collector on Aurora is
`/lus/flare/projects/E3SMinput/baselines/performance_archive/pace_archive_aurora.sh`.
Each run it:

1. Moves completed executions out of `<user>/<case>/<execution-id>/` into a new
   top-level `performance_archive_<timestamp>/` batch.
2. Uploads that batch to PACE with `pace-upload3`, which works in a
   `pace-exps-<user>-<timestamp>/` tree.
3. Moves the batch to `OLD_PERF/<YYYY-MM>/`.

| Root | Path |
| --- | --- |
| Staging (`PERF_ARCHIVE_ROOT`) | `/lus/flare/projects/E3SMinput/baselines/performance_archive` |
| Archive (`OLD_PERF_ARCHIVE_ROOT`) | `/lus/flare/projects/E3SMinput/baselines/performance_archive/OLD_PERF` |

`aurora.config` uses these as defaults. Unlike Chrysalis, the archive root is
inside the staging root. Staging scans therefore skip `OLD_PERF`, top-level
`performance_archive_*` batches, and `pace-exps-*` trees; those executions are
either already archived or still on their way to `OLD_PERF`.

A batch whose upload is interrupted stays at the top level instead of moving to
`OLD_PERF`. Neither scan mode reads it. Move it into `OLD_PERF/<YYYY-MM>/`, as
the collector would have, to have the archive scan pick it up.

Because staging output only lives until the next PACE run, the archive scan of
`OLD_PERF` is the authoritative source for Aurora. Staging scans add runs that
PACE has not processed yet.

## Still to confirm on Aurora

| Item | Why it is open |
| --- | --- |
| Scheduler | Which host and account run `pace_archive_aurora.sh`, and whether SimBoard's job can run the same way. |
| Scheduler identity | Which account owns the SimBoard job, with at least one backup operator. |
| API credentials | A dedicated SimBoard service account for Aurora, stored as a protected variable or protected file. |
| Network egress | Whether the scheduling host can reach the SimBoard API over HTTPS. |
| Diagnostics | Whether Aurora publishes zppy diagnostics, and where. |

Diagnostics scheduling is disabled for Aurora
(`SIMBOARD_DIAGNOSTICS_ENABLED=false`), so `make ops-init-cron site=aurora`
produces staging and archive jobs only. Enable it after adding Aurora to
`backend/app/scripts/ingestion/diagnostics_archives.py` with a verified root and
public URL.

## Validate on Aurora

Use a personal account for this step; it reads the archive and uploads nothing.

1. Provision a deployment and run an offline archive dry run:

   ```bash
   make ops-provision SIMBOARD_ROOT=<deployment-root>
   cd <deployment-root>/repository/simboard
   DRY_RUN_USE_REMOTE_STATE=false \
   make ingest-dry-run machine=aurora env=dev scan_mode=archive \
     SIMBOARD_ROOT=<deployment-root>
   ```

   The run summary in `operations/raw_logs/` reports cases found and executions
   accepted or rejected, with reasons, and no requests are made.

2. Repeat with `scan_mode=staging` and confirm only `<user>/<case>/<execution-id>`
   directories are scanned.

3. Compare the archive dry run's accepted executions with PACE's Aurora
   experiments. SimBoard validates more strictly than PACE, so some PACE-visible
   runs may be rejected; the rejection reasons say why.

## Load existing PACE history

`OLD_PERF` holds every batch PACE has processed on Aurora, and the site's
default archive lower bound (`2025-01`) covers all of it. After the service
account is in place:

1. Run a bounded live upload to development and compare the records with PACE:

   ```bash
   make ingest-apply machine=aurora env=dev scan_mode=archive \
     SIMBOARD_ROOT=<deployment-root> MAX_CASES_PER_RUN=5
   ```

2. Run the full archive scan against development, then production. Completed
   snapshots are checkpointed, so reruns skip them.

## Enable scheduled ingestion

After validation and an agreed owner:

1. Create the Aurora service account and token (see
   [HPC API Token Authentication](hpc-api-token-authentication.md)), then
   `make ops-init-env site=aurora SIMBOARD_ROOT=<deployment-root>`.
2. Schedule the launcher. For cron, `make ops-init-cron site=aurora` renders the
   schedule. For another scheduler, invoke the same command:

   ```bash
   SIMBOARD_ROOT=<deployment-root> \
   SIMBOARD_ENV_FILE=<deployment-root>/operations/env.dev.sh \
   <deployment-root>/repository/simboard/backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh \
     aurora archive
   ```

   The launcher requires `flock`.

The scans are read-only, so they can run alongside PACE's collector against the
same directories.

## Ownership

Schedule the job under a project-owned identity where ALCF provides one. If only
a personal account can own it, keep the deployment in shared project storage,
grant a backup operator access with `make ops-configure-access`, and use a
service-account token rather than personal credentials.
