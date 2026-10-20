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

Staging scans follow ingestion's `root/hpc-username/case/execution` layout. They skip top-level `performance_archive_*` batches and `pace-exps-*` trees and do not descend into execution contents. Use archive scans for historical archive layouts.

For source-directory bootstrap, `machine=perlmutter` selects the scan configuration, not a required execution machine. Like general ingestion, backfill reads each execution's machine from its metadata and uses its canonical name for owner lookup and mapping writes. A NERSC scan can therefore map Perlmutter, Muller, and Alvarez executions. Missing machine metadata and API errors for unknown machines remain failures; backfill never substitutes the scanner's machine.

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

### Chrysalis v3 production cases

Add `--v3` with `machine=chrysalis` to limit both source-directory bootstrap and
metadata updates to the documented v3 production case names. This reuses the
existing v3 case identities, not a separate case list or guessed filesystem paths.
“Production” describes the simulations; `env` still selects the API deployment.

```bash
make metadata-backfill machine=chrysalis env=dev \
  SIMBOARD_ROOT=/path/to/simboard_root \
  args='--v3 --fields source-directories --sources archive --dry-run'
```

The archive root defaults to `/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF` on LCRC.
In v3 mode, the archive start defaults to the existing v3 ingestor's `2024-01`
lower bound rather than the general Chrysalis `2025-01` default. An explicit
`--archive-start` or `ARCHIVE_YEAR_START` still takes precedence. Root overrides
and archive-end bounds retain their normal behavior. Review the printed scope
before applying; an existing environment override can exclude older archives.

V3 mode supports both staging and archive sources and preserves optional exact
case/user filters. A case filter must name a documented v3 case. Source identity
must identify Chrysalis; v3 mode does not substitute the machine from the path.

After reviewing and applying the source-directory mappings with separate
authorization, preview the metadata update:

```bash
make metadata-backfill machine=chrysalis env=dev \
  SIMBOARD_ROOT=/path/to/simboard_root \
  args='--v3 --fields simulation-dates run-script --sources archive --dry-run'
```

Metadata updates reuse the stored execution-to-directory mappings. They do not
rescan archives or infer missing paths. Add `--overwrite` only when correcting
existing values is intended; apply still requires separate authorization.

For metadata updates, `--sources both` prefers existing mapped archive directories
and reads staging only when no mapped archive directory remains. Missing directories
are ignored during selection; the record fails if neither source is available.
All directories of the selected kind retain identity and conflict checks. Staging
is not inspected when archive directories are selected, so cross-kind conflicts
are not checked.

Permission errors, non-directory paths, and other filesystem errors fail selection.
Once a source kind is selected, read, parse, and identity errors fail the record
without fallback, as does finding no requested metadata. A directory disappearing
after selection also fails the record. Explicit `--sources archive` and
`--sources staging` remain strict: every selected mapping must be readable.
These rules do not change source-directory bootstrap.

### Review and apply

Dry runs resolve owners through the API without writing mappings. **`matched` means the existing owner resolved**, not that a new mapping was inserted.

1. Check the printed API target, mode, and effective scope.
2. Review the dry-run results and obtain explicit authorization.
3. Replace `--dry-run` with `--apply`.

Reruns retain existing mappings without duplicates. Missing required identity files (`skipped_incomplete`) and unresolved owners (`skipped_no_owner`) are expected skips, not failures. Actual read, parse, API, and scan errors produce a nonzero exit status. Missing files are never guessed.

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
{"matched": 0, "skipped_no_owner": 0, "skipped_incomplete": 0, "failed": 0}
```

This scan finished without finding a path-level match. Replace placeholders such as `exact-case-name` and `exact-user` with real values, and check the configured roots and archive bounds.

**Directory matches are not successful updates.** Source metadata can still fail identity validation after a directory matches. A `skipped_no_owner` JSON outcome means the API could not find the existing database owner:

```json
{"path": "/path/to/performance_archive/alice/my-case/123.250101-000000", "outcome": "skipped_no_owner", "dry_run": true}
```

#### Output streams and pauses

- Progress logs go to **stderr**. Existing configuration, per-record JSON, and final summaries remain on **stdout**.
- A readable `RUN_SUMMARY` block also goes to **stderr** after the JSON totals. It distinguishes incomplete executions and unresolved database owners from read/parse/API/scan failures.
- No persistent log file is created.
- Directory progress is not a timed heartbeat. A blocked filesystem operation or in-flight API request can still pause output.
- Retry events make subsequent API waits visible:

```text
INFO event=backfill_api_retry attempt=1 delay_seconds=1 status_code=503
```

#### Readable final summary

For example, a dry run with one resolved owner, one unresolved owner, one
incomplete execution, and one source-read failure ends with the following block (timestamps and logger prefixes
omitted):

```text
INFO RUN_SUMMARY Metadata backfill
INFO RUN_SUMMARY Mode: dry run
INFO RUN_SUMMARY Existing owners matched: 1
INFO RUN_SUMMARY Skipped without existing owner: 1
INFO RUN_SUMMARY Skipped incomplete executions: 1
INFO RUN_SUMMARY Read/parse/API/scan failures: 1
INFO RUN_SUMMARY Database writes: disabled (dry run)
INFO RUN_SUMMARY Status: failure
INFO RUN_SUMMARY Exit code: 1
INFO RUN_SUMMARY Elapsed seconds: 12.345
```

JSON totals report `matched`, `skipped_no_owner`, `skipped_incomplete`, and `failed`
separately. The `failed` count excludes expected skips. Source-directory backfill
returns exit code `0` when no actual errors occur, including runs where every
candidate is skipped. Success does not imply any owner matched or any mapping
was written. This replaces the previous `unresolved` outcome and its inclusion
in `failed`.

An unresolved owner is not an API outage; it means no exact match exists in the
selected database for machine, case name, HPC username, and execution ID. Backfill
skips it without creating records; normal ingestion handles eligible new executions.

`Missing identity file case_docs_env_case` means no file matched the supported
`CaseDocs*/env_case.xml.<suffix>.gz` pattern. The file may be absent, uncompressed,
or named differently. Inspect the actual source filenames before changing parser
rules; backfill never infers missing identity from directory names. Missing either
required identity file (`case_docs_env_case` or `e3sm_timing`) produces a
`skipped_incomplete` outcome with the reason. This means incomplete for backfill,
not proof that the simulation failed. Missing machine metadata, ambiguous or
malformed metadata, and permission errors remain failures.

For database-first updates, the summary shows records with **planned changes**
in dry-run mode, **records changed** in apply mode, unchanged records, and
record/request failures. Matched owners and planned changes do not mean writes
occurred during a dry run.

## 2. Backfill execution metadata

Once mappings exist, select database records and read their mapped directories. This step requires no archive-wide scan or filesystem roots.

Database-first updates remain scoped to the selected `machine`. Mapped source metadata must match that machine and the selected database owner's identity; a different source machine remains a failure in this step.

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

Legacy Spin mappings under `/performance_archive` and `/OLD_PERF` are read through
`PERF_SOURCE_ROOT` and `OLD_PERF_SOURCE_ROOT`, respectively, when configured.
Perlmutter's site config defaults these variables to absolute NERSC host paths.
Exported values or the protected environment file can override these defaults;
configured source roots must be absolute. Other stored paths remain unchanged.
This translation affects reads only, not stored mappings or owner identity checks.

### Review and apply

1. Review the dry-run results and obtain authorization.
2. Replace `--dry-run` with `--apply`.
3. Validate the small subset and rerun it to check idempotency before expanding scope.

Dry-run and apply independently read current records; there is no saved preview session. Correction writes reject updates if the expected old values have changed.

## Direct Python invocation

Direct Python invocation requires explicit `--machine` and exported `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN`, including for dry runs. The Python command does not load shell files itself.

## Adding future fields

Extend the same command with explicit extraction/update functions, validated payload fields, tests, and documentation. Database migrations and normal-ingestion support remain separate from historical backfill.
