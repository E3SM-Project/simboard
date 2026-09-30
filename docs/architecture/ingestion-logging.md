# Ingestion Logging

The NERSC, HPC-upload, and targeted v3 command-line runners share an
observational logging contract. Logging does not change selection, retries,
persistence, checkpoints, or process outcomes.

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

Every runner line has a UTC timestamp, severity, category, and invocation
`run_id`. For example (timestamps omitted here):

```text
INFO CONFIG run_id=r1 event=run_started scan_mode=staging
DEBUG EXECUTION_DETAIL run_id=r1 event=execution_decision case=a execution_id=100.1-1 reason=new_execution outcome=selected
DEBUG EXECUTION_DETAIL run_id=r1 event=execution_decision case=a execution_id=101.1-1 reason=already_processed outcome=skipped
INFO CASE_SUMMARY run_id=r1 event=case_discovered case=a executions.total=2 executions.selected=1 executions.skipped=1 executions.incomplete=0 executions.invalid=0 executions.unreadable=0 executions.deferred=0
INFO CASE_SUMMARY run_id=r1 event=case_submission case=a outcome=succeeded attempts=1
INFO RUN_SUMMARY run_id=r1 Executions found: 2
INFO RUN_SUMMARY run_id=r1   Selected: 1
INFO RUN_SUMMARY run_id=r1   Skipped: 1
```

The full readable summary includes all execution counts, case selection counts,
case submission outcomes, status, exit code, and elapsed seconds. Selection is
not successful ingestion. Failed submission does not change discovery counts.

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

## Canonical metrics

Each successful or handled-failure invocation emits one INFO record:

```text
<UTC prefix> INFO RUN_SUMMARY run_id=r1 event=run_metrics payload=<compact JSON>
```

Parse the JSON occupying the rest of the physical line after
`event=run_metrics payload=`. Do not aggregate readable summaries or other
events. The following example is expanded only for documentation; actual JSON
is a single line:

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
  "executions": {
    "total": 2, "selected": 1, "skipped": 1, "incomplete": 0,
    "invalid": 0, "unreadable": 0, "deferred": 0
  },
  "cases": {
    "found": 1, "eligible": 1, "selected": 1, "deferred": 0,
    "succeeded": 1, "failed": 0, "not_attempted": 0
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
