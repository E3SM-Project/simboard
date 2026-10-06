# Ingestion Logging

The NERSC, HPC-upload, and targeted v3 command-line runners share an
observational logging contract. Logging does not change selection, retries,
persistence, checkpoints, or process outcomes.

This document is the single maintained source of truth for logging terms, public
events, and metrics. Other architecture and operations documents link here rather
than redefine the contract. Ingestion domain and persisted-state behavior are
described in [Metadata Ingestion Architecture](metadata-ingestion.md).

## Levels and categories

Set `SIMBOARD_INGESTION_LOG_LEVEL` when invoking a runner or the site launcher:

```bash
SIMBOARD_INGESTION_LOG_LEVEL=DEBUG python -m app.scripts.ingestion.nersc_archive_ingestor
SIMBOARD_INGESTION_LOG_LEVEL=INFO ./site_ingestion_launcher.sh chrysalis staging
```

INFO is the default. DEBUG, INFO, WARNING, ERROR, and CRITICAL are accepted
(case-insensitive, with surrounding whitespace ignored). Invalid levels stop
the invocation with an error and nonzero exit code.

| Category | Contents |
| --- | --- |
| `CONFIG` | Startup configuration and operational errors |
| `CASE_SUMMARY` | One discovery summary per case and separate submission results |
| `EXECUTION_DETAIL` | DEBUG decisions, validation/cache counters, progress, and request timing |
| `RUN_SUMMARY` | Readable totals and one canonical metrics record |

Recoverable request failures use WARNING; terminal failures use ERROR.
Execution decisions and progress are DEBUG, not INFO. Ingestion's UTC handler
does not enable third-party DEBUG output. Credentials and URL secrets are
redacted before rendering.

## Case and execution structure

Every runner line has a UTC timestamp, severity, and category. Each ingestion
job has its own log, so its invocation ID appears once in the startup header
and inside the final `run_metrics` payload, not in every line's prefix.
For example (timestamps omitted here):

```text
INFO CONFIG event=invocation_started Run ID: r1
INFO CONFIG Machine: chrysalis
INFO CONFIG Mode: dry run
INFO CONFIG Scan: staging
INFO CONFIG API: https://simboard-dev-api.e3sm.org
INFO CONFIG Remote state: enabled (read-only)
INFO CONFIG API token: configured
INFO CONFIG Archive root: /lcrc/group/e3sm/PERF_Chrysalis/performance_archive
INFO CONFIG Archive range: not applicable (staging)
INFO CONFIG Maximum cases: unlimited
INFO CONFIG Maximum attempts: 3
INFO CONFIG Request timeout: 60 seconds
DEBUG EXECUTION_DETAIL event=execution_decision case=a execution_id=100.1-1 outcome=selected reason=new_execution
DEBUG EXECUTION_DETAIL event=execution_decision case=a execution_id=101.1-1 outcome=skipped reason=already_processed
INFO CASE_SUMMARY event=case_discovered case=a EXECUTIONS total=2 selected=1 skipped=1 incomplete=0 invalid=0 unreadable=0 deferred=0
INFO RUN_SUMMARY Cases found: 1
INFO RUN_SUMMARY Cases eligible: 1
INFO RUN_SUMMARY   Selected: 1
INFO RUN_SUMMARY   Deferred: 0
INFO RUN_SUMMARY Selected case outcomes: 1
INFO RUN_SUMMARY   Succeeded: 0
INFO RUN_SUMMARY   Failed: 0
INFO RUN_SUMMARY   Not attempted: 1
INFO RUN_SUMMARY Executions found: 2
INFO RUN_SUMMARY   Selected: 1
INFO RUN_SUMMARY   Skipped: 1
```

The full readable summary lists case discovery/selection counts and case
submission outcomes first, then execution counts, followed by status, exit code,
and elapsed seconds. Selection is not successful ingestion. Failed submission
does not change discovery counts.

The configuration block is emitted once after validation and before API access
or discovery. Archive scans show their configured year range; absent bounds are
displayed as `unbounded`. Offline dry runs show `Remote state: disabled (offline)`.
Targeted v3 scans also display their source URL. Only token presence is shown,
never the token itself. Configuration failures retain the invocation header but
do not print an unvalidated configuration block. Invalid logging levels include
the invocation ID in their error record. Normal level filtering still applies:
startup and final metrics are INFO and are suppressed at higher thresholds.

### Public events

| Event | Fields and purpose |
| --- | --- |
| `invocation_started` | Identifies an invocation before configuration validation. |
| Readable `CONFIG` block | Validated API base URL, archive scope, runtime options, and token presence; never the credential itself. Replaces CLI rendering of internal `run_started` / `v3_run_started` and `startup_configuration_*` events. |
| `case_discovered` | `case`, followed by one `EXECUTIONS` label, `total`, and all six execution outcomes defined below. |
| `case_submission` | Successful INFO records contain only `case` and `outcome=succeeded`. Failed ERROR records add `attempts`, `status_code`, and `error` with `outcome=failed`. |
| `execution_decision` | DEBUG: `case`, `execution_id`, `outcome`, and `reason`; relevant validation codes, missing-file specifications, or error detail may follow. |
| `run_metrics` | INFO: `payload` contains the authoritative JSON record defined below. |

Readable run totals and final status are emitted by the same finalizer as
`run_metrics`. There are no separate legacy run/dry-run summary blocks, case-begin
records, dry-run candidate lists, or duplicate run-finish events.

### DEBUG diagnostics

These events support troubleshooting; they are not aggregation inputs:

| Event | Fields and purpose |
| --- | --- |
| `archive_scan_started` | `scan_mode`, `archive_root`; begins a filesystem traversal. |
| `archive_scan_progress` / `archive_scan_completed` | `current_dir`, `directories_visited`, `duration_seconds`; traversal progress/completion without repeated validation counters. Archive scope may require multiple traversals. |
| `scan_completed` | `submission_qualified_cases`, `selected_submission_cases`, and the validation counters below; emitted once after run-level selection. |
| `archive_created` | `case_path`, `selected_execution_count`, `archive_bytes`, `duration_seconds`; one staged delta archive reused across retries. |
| `case_upload_attempt` | `case_path`, `attempt`, `archive_bytes`, `duration_seconds`; multipart transport timing. |
| `case_ingestion_attempt_completed` | `case_path`, `attempt`, `duration_seconds`; elapsed time per case request. No additional retry-sequence timing record. |
| `case_submission_details` | `case_path`, `attempts`, `created_count`, `duplicate_count`, `error_count`; successful backend response details, excluded from canonical totals. |
| `v3_ingestion_summary` | Targeted v3 reconciliation diagnostics; not an additional canonical summary. |

Recoverable operational problems remain WARNING even when DEBUG diagnostics are
disabled. Terminal failures remain ERROR. Classification uses explicit event
groups, not substring guesses. Shared tools outside a runner invocation retain
their existing INFO rendering policy and do not emit runner metrics.

### Internal counter mappings

These names describe internal observations, not an alternative metrics contract.
Validation/cache counters are kept separate from final execution outcomes; do
not combine the two populations or infer public counts from validation totals.

| Internal field | Meaning or public mapping |
| --- | --- |
| `submission_qualified_cases` | `cases.eligible`; cases eligible before the limit. |
| `selected_submission_cases` | `cases.selected`; cases selected after the limit. |
| `execution_dirs_scanned` | Matching execution directories examined by discovery, including cached outcomes. |
| `execution_dirs_accepted` | Examined directories retained as valid, including cached accepted outcomes; not submission success. |
| `skipped_incomplete` / `skipped_invalid` | Discovery validation/cache rejections for missing or invalid metadata. |
| `skipped_transient` | Discovery filesystem-access failures; not persisted. |
| `accepted_execution_ids` / per-case `accepted` | Final selection observation mapped to `executions.selected`. |
| `rejected_existing_execution_ids` / per-case `rejected_existing` | Final already-processed observation mapped to `executions.skipped`. |
| `rejected_incomplete_execution_ids` / per-case `rejected_incomplete` | Final missing-metadata observation mapped to `executions.incomplete`. |
| `rejected_invalid_execution_ids` / per-case `rejected_invalid` | Final invalid-metadata observation mapped to `executions.invalid`. |
| `transient_execution_ids` / per-case `transient` | Final inaccessible-files observation mapped to `executions.unreadable`. |
| `deferred_execution_ids` / per-case `deferred` | Final limit-excluded observation mapped to `executions.deferred`. |

Only the validation/cache counters are included in `scan_completed`; final
outcome counters are represented by case summaries and canonical metrics rather
than repeated there. Stored discovery `accepted` means validation succeeded and
can later result in selection, deferral, or skipping; it is not the same as a
final reporting outcome.

### Case counts

| Field | Meaning |
| --- | --- |
| `found` | Case paths with at least one execution observation |
| `eligible` | Cases eligible before applying the limit |
| `selected` | Cases selected after applying the limit |
| `deferred` | Eligible cases excluded by the limit |
| `succeeded` | Successful case-submission operations |
| `failed` | Failed case-submission operations |
| `not_attempted` | Selected cases not submitted |

When counts are available:

```text
eligible = selected + deferred
selected = succeeded + failed + not_attempted
```

`found`, `eligible`, and `selected` are nested populations, not additive
siblings. A case can contain several execution outcomes. Submission success
does not mean executions were newly created; backend creation/duplicate/parser
totals are not part of this contract.

### Execution counts

An observation is an execution ID at one case path visited within the scan
scope. Filtered paths and completed snapshots that are not visited are excluded.
Each observation receives one final discovery outcome:

| Field | Meaning |
| --- | --- |
| `total` | Sum of the six outcomes |
| `selected` | Selected for submission |
| `skipped` | Already processed |
| `incomplete` | Required metadata missing |
| `invalid` | Metadata failed validation |
| `unreadable` | Files could not be accessed |
| `deferred` | Eligible but excluded by the case limit |

```text
total = selected + skipped + incomplete + invalid + unreadable + deferred
run.executions.<field> = sum(case.executions.<field>)
```

Counts come from final case decisions, not a mixture of fresh-validation and
cached-result counters. The same logical execution appearing at different
archive paths, or in successive runs, contributes separate observations.

## Canonical metrics

Each successful or handled-failure invocation emits one INFO record:

```text
<UTC prefix> INFO RUN_SUMMARY event=run_metrics payload=<compact JSON>
```

Parse the JSON occupying the rest of the physical line after
`event=run_metrics payload=`. Do not aggregate readable summaries or other
events. The payload presents `cases` before `executions`, matching the readable
summary. This is presentation order only; consumers should access fields by name.
The following example is expanded only for documentation; actual JSON is a
single line:

```json
{
  "schema_version": 1,
  "run_id": "r1",
  "runner": "app.scripts.ingestion.nersc_archive_ingestor",
  "machine": "perlmutter",
  "environment": "env.dev.sh",
  "scan_mode": "staging",
  "dry_run": false,
  "started_at": "2026-09-30T15:00:00+00:00",
  "finished_at": "2026-09-30T15:00:08+00:00",
  "duration_seconds": 8.0,
  "status": "success",
  "exit_code": 0,
  "discovery_complete": true,
  "submission_complete": true,
  "cases": {
    "found": 1, "eligible": 1, "selected": 1, "deferred": 0,
    "succeeded": 1, "failed": 0, "not_attempted": 0
  },
  "executions": {
    "total": 2, "selected": 1, "skipped": 1, "incomplete": 0,
    "invalid": 0, "unreadable": 0, "deferred": 0
  }
}
```

- Counts are nonnegative integers or `null` when unavailable. Null is not zero.
- Identities are null when unavailable. `environment` is the API environment
  filename's basename; use distinct basenames for distinct deployment targets.
- Timestamps are UTC; duration is monotonic elapsed seconds.
- `status` is `success` for exit code zero, otherwise `failure`.
- `discovery_complete` means the scan finished without known traversal gaps.
- `submission_complete` means the submission loop finished and all selected
  cases have attempted outcomes, not that all succeeded. It is false for dry
  runs and failures before the submission loop, even if no cases were selected.
- With completed dry-run selection, successes/failures are zero and
  `not_attempted=selected`. Before submission, known selected cases remain
  not attempted. Before scan completion, unavailable counts remain null.
- WARNING/ERROR/CRITICAL suppress informational metrics. Aggregation-enabled
  jobs must use INFO or DEBUG.
- Unexpected exceptions and uncatchable termination need not emit final
  metrics. A start without metrics is unfinished/unknown, not zero activity.
- Compatible optional fields may be added; changed types or meanings require
  a new schema version.

## Future aggregation

Deduplicate canonical records by `run_id`. Group compatible records by runner,
machine, environment, scan mode, and dry-run status. Exclude dry runs from live
submission totals. Sum the same leaf fields or durations across runs; never
add parent counts to their children. Attribute daily reports to UTC completion
date. Include contributing, incomplete, and unavailable-run coverage alongside
totals. For example, three known runs with `selected=2` total six selection
observations, not necessarily six unique executions.

No summarization service is implemented here. Existing work-in-progress scripts
must adapt to this contract; old summary events are not a compatibility API.

## Launcher failures

The site launcher captures output before sourcing configuration or checking
Python when `SIMBOARD_ROOT` permits creation of a raw log. Each filename includes
a PID to avoid collisions. Its filename uses the scheduler-provided environment
basename; if site configuration supplies that variable later, the filename's
initial environment label is provisional (the Python metrics have the final
identity). Launcher start/finish events also cover early exits
and lock contention; they are not Python `run_metrics` records.

If the root is missing or a log cannot be created, errors remain on stderr.
Configure scheduler-level output capture for these failures. No system can
guarantee file logging when the destination is unwritable. Configuration and
environment files are trusted shell scripts; never enable tracing or echo
credentials from them. Protected API environment sourcing suppresses its
stdout/stderr because malformed assignments can print tokens. The launcher
records that phase and its final exit status instead of unsafe shell diagnostics.
