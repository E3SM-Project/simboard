# Historical metadata backfill

Backfill the **NERSC-hosted staging PostgreSQL database** through its API deployment. The database target is independent of the performance staging and archive filesystem sources. No production backfill is needed now.

## Prerequisites

1. **Deploy the updated backend.** It provides source-directory dry-run support and metadata selection/update endpoints.
2. **Configure API access** using one of the options below.
3. **Obtain explicit authorization before applying changes.** Implementation approval does not authorize writes to the live staging database.

The Make command loads the selected machine's site config and a protected API environment file. Both `machine` and `env` are required.

| API configuration             | Usage                                                                                                                               |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Existing operations workspace | Set `SIMBOARD_ROOT=/path/to/simboard_root`. `env=dev` loads `$SIMBOARD_ROOT/operations/env.dev.sh`; `env=prod` loads `env.prod.sh`. |
| Explicit environment file     | Set `env_file=/path/to/protected/env.dev.sh`. This overrides the operations-file lookup and does not require `SIMBOARD_ROOT`.       |

Use the existing operations workspace for `SIMBOARD_ROOT`, not a performance staging or archive root. No machine-to-workspace mapping is assumed.

Never place tokens in command arguments or logs.

## 1. Bootstrap source-directory mappings

Start with a small case/user filter and both source types:

```bash
make metadata-backfill machine=perlmutter env=dev \
  SIMBOARD_ROOT=/path/to/simboard_root \
  args='--fields source-directories --sources both --case-name exact-case-name --hpc-username exact-user --dry-run'
```

The command reads identity metadata and maps staging/archive directories to **matching existing records**. It ignores ingestion checkpoints and processed-execution skips. It does not upload data, create catalog records, or change ingestion state.

### Review the scan scope

| Setting       | Default                                                                          | CLI override      |
| ------------- | -------------------------------------------------------------------------------- | ----------------- |
| Staging root  | Site config: `PERF_ARCHIVE_ROOT`                                                 | `--staging-root`  |
| Archive root  | Site config: `OLD_PERF_ARCHIVE_ROOT`                                             | `--archive-root`  |
| Archive start | `ARCHIVE_YEAR_START`, otherwise the site's `SIMBOARD_DEFAULT_ARCHIVE_YEAR_START` | `--archive-start` |
| Archive end   | `ARCHIVE_YEAR_END`; unbounded when unset                                         | `--archive-end`   |

Archive bounds apply only to archive directories. Review the printed effective scope, especially the lower bound when backfilling older records.

Site configs supply root defaults only when variables are unset. Exported shell values or assignments in the protected environment file override site defaults; explicit CLI arguments take precedence over both.

Case/user filters are optional. Keep them for validation runs and focused retries; omit them to select the full configured scope. Set the machine through Make's `machine` argument, not `--machine` inside `args`.

### Review and apply

Dry runs resolve owners through the API without writing mappings. **`matched` means the existing owner resolved**, not that a new mapping was inserted.

1. Check the printed API target, mode, and effective scope.
2. Review the dry-run results and obtain explicit authorization.
3. Replace `--dry-run` with `--apply`.

Reruns retain existing mappings without duplicates. Failures and unresolved owners produce a nonzero exit status. Missing files are never guessed.

Stored paths record observations; they do not guarantee current availability.

### Console progress

Backfill reuses [ingestion's structured logging and credential redaction](../architecture/ingestion-logging.md), without its runner metrics or upload workflow.

#### What you will see

| Event | Meaning |
| --- | --- |
| `backfill_scan_started` | Starts a staging or archive scan and identifies its root and filters. |
| `backfill_scan_progress` | Reports the current directory, directories visited, matching execution directories, and elapsed seconds. |
| `backfill_scan_completed` | Reports final scan counts. `traversal_complete=false` means the scan did not finish. |
| `backfill_scan_no_matches` | A completed scan found no execution directories matching the path-level case/user filters. |
| `backfill_api_retry` | Reports a transient API failure's attempt, status code, and wait duration before retrying. |
| `backfill_page_started` / `backfill_page_completed` | Reports database-first page progress. `failed_total` is cumulative across pages, not a per-page count. |

Progress follows ingestion's existing directory-count interval. It appears even when filters match nothing, but small scans may show only start and completion.

#### Example: a scan with no matches

Illustrative output below omits timestamps, logger prefixes, and some fields:

```text
INFO event=backfill_scan_started source=archive root=/path/to/OLD_PERF directories_visited=0 matching_executions=0
INFO event=backfill_scan_progress source=archive current_dir=/path/to/OLD_PERF/2025-01 directories_visited=250 matching_executions=0 duration_seconds=12.4
INFO event=backfill_scan_completed source=archive directories_visited=310 matching_executions=0 duration_seconds=15.1 traversal_complete=true
INFO event=backfill_scan_no_matches source=archive directories_visited=310 matching_executions=0
{"matched": 0, "failed": 0}
```

This scan finished without finding a path-level match. Replace placeholders such as `exact-case-name` and `exact-user` with real values, and check the configured roots and archive bounds.

**Directory matches are not successful updates.** Source metadata can still fail identity validation after a directory matches. An `unresolved` JSON outcome means the API could not find the existing database owner:

```json
{"path": "/path/to/performance_archive/alice/my-case/123.250101-000000", "outcome": "unresolved", "dry_run": true}
```

#### Output streams and pauses

- Progress logs go to **stderr**. Existing configuration, per-record JSON, and final summaries remain on **stdout**.
- No persistent log file is created.
- Directory progress is not a timed heartbeat. A blocked filesystem operation or in-flight API request can still pause output.
- Retry events make subsequent API waits visible:

```text
INFO event=backfill_api_retry attempt=1 delay_seconds=1 status_code=503
```

## 2. Backfill execution metadata

Once mappings exist, select database records and read their mapped directories. This step requires no archive-wide scan or filesystem roots.

```bash
make metadata-backfill machine=perlmutter env=dev \
  SIMBOARD_ROOT=/path/to/simboard_root \
  args='--fields simulation-dates run-script --sources both --case-name exact-case-name --hpc-username exact-user --dry-run --overwrite'
```

### Update behavior

- **Without `--overwrite`:** populate only missing values.
- **With `--overwrite`:** also correct existing simulation dates and CIME wrapper links.
- Missing source values never clear stored metadata. Unrelated artifacts remain intact.
- Conflicts, identity mismatches, unavailable mappings, and failures are reported. If any selected mapped path cannot be read safely, that record is not updated.

Simulation end dates use the current parser's initial driver `Stop Time`, not actual termination time.

This database-first step does not inherit filesystem roots or archive bounds from the environment.

### Review and apply

1. Review the dry-run results and obtain authorization.
2. Replace `--dry-run` with `--apply`.
3. Validate the small subset and rerun it to check idempotency before expanding scope.

Dry-run and apply independently read current records; there is no saved preview session. Correction writes reject updates if the expected old values have changed.

## Direct Python invocation

Direct Python invocation requires explicit `--machine` and exported `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`, including for dry runs. The Python command does not load shell files itself.

## Adding future fields

Extend the same command with explicit extraction/update functions, validated payload fields, tests, and documentation. Database migrations and normal-ingestion support remain separate from historical backfill.
