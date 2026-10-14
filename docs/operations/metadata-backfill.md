# Historical metadata backfill

The initial target is the NERSC-hosted staging PostgreSQL database, accessed
through its API deployment. This database target is independent of performance
staging and archive filesystem sources. No production backfill is needed now.

Load the existing protected API environment for the target deployment. The
command requires `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`, including for dry runs. Never
place tokens in command arguments or logs.

Deploy the updated backend first: it adds source-directory dry-run support and
metadata selection/update endpoints. Implementation approval does not authorize
applying changes to the live staging database.

## Bootstrap directory mappings

Start with a small case filter and both source types:

```bash
make metadata-backfill args='--machine perlmutter --fields source-directories --sources both --staging-root /path/to/performance_archive --archive-root /path/to/OLD_PERF --archive-start 2025-01 --archive-end 2025-02 --case-name exact-case-name --hpc-username exact-user --dry-run'
```

Archive bounds apply only to archive directories. The command deliberately
ignores ingestion checkpoints and processed-execution skips. It reads identity
metadata and adds staging/archive mappings only to matching existing records.
It does not upload data, create catalog records, or change ingestion state.

Dry runs resolve owners through the API without writing mappings. `matched`
means the existing owner resolved; it does not mean a new mapping was inserted.
After explicit authorization, replace `--dry-run` with `--apply`. Rerun safely:
existing mappings are retained without duplicates. Failures and unresolved
owners produce a nonzero exit status. Missing files are never guessed.

The command prints its API target and mode before scanning. Check both before
applying. Stored paths are observations, not guarantees of current availability.

## Backfill execution metadata

Once mappings exist, select existing database records and read their mapped
directories. No archive-wide scan or filesystem roots are needed:

```bash
make metadata-backfill args='--machine perlmutter --fields simulation-dates run-script --sources both --case-name exact-case-name --hpc-username exact-user --dry-run --overwrite'
```

Without `--overwrite`, only missing values are populated. Corrections of existing
simulation dates and CIME wrapper links require `--overwrite`. Missing source
values never clear stored metadata. Conflicting observations, identity mismatches,
unavailable mappings, and failures are reported. If any selected mapped path
cannot be read safely, that record is not updated. Unrelated artifacts remain intact.
Simulation end dates retain the current parser's initial driver `Stop Time`
semantics, not actual termination time.

Dry-run and apply independently read current records; there is no saved preview
session. Correction writes reject changes to expected old values. Review the
dry-run, obtain authorization, then replace `--dry-run` with `--apply`. Validate a
small subset first and rerun it to check idempotency before expanding scope.

Future fields should add explicit extraction/update functions, validated payload
fields, tests, and documentation to the same command. Database migrations and
normal-ingestion support remain separate from historical backfill.
