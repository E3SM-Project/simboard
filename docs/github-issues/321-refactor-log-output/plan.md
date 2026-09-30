# Issue #321: Ingestion logging refactor plan (branch: `devops/321-refactor-log-output`)

## Problem

Ingestion logs are too verbose. Reduce routine noise, make summaries readable, and provide a stable record that a future summarization module can use to calculate totals without double-counting.

## Scope

### 1. Configure logging and reduce noise

- Add `SIMBOARD_INGESTION_LOG_LEVEL`, defaulting to INFO. Accept standard severity levels; reject invalid values with a clear error and nonzero exit.
- Move routine already-processed, incomplete, deferred, progress, and request-detail events to DEBUG.
- Keep configuration, compact case outcomes, and summaries at INFO. Use WARNING for recoverable operational problems and ERROR for terminal failures.
- Use `CONFIG`, `CASE_SUMMARY`, and `RUN_SUMMARY` categories at INFO, plus `EXECUTION_DETAIL` at DEBUG. Event names and fields may change to simplify the new contract.
- Configure only ingestion logging; do not enable unrelated DEBUG output or duplicate handlers.

### 2. Emit one authoritative metrics record per run

- Create a unique `run_id` and start time before configuration validation. Include the ID in ingestion events and a run-start record.
- Add logging-only run context and final metrics emission around existing runner paths. Emit `event=run_metrics payload=<compact JSON>` once after success or a handled failure; JSON occupies the rest of the line after the marker.
- Summary/detail events are diagnostic only. A future summarizer must aggregate only `run_metrics` and deduplicate by `run_id`.
- Emit metrics at INFO. Aggregation requires INFO or DEBUG logs; WARNING/ERROR logs intentionally do not provide complete metrics coverage.
- Do not promise a final record after a crash or uncatchable termination. A start record without final metrics indicates an unfinished run, not zero activity.

The JSON contract uses these fields:

| Fields | Meaning |
| --- | --- |
| `schema_version`, `run_id` | Integer contract version and unique invocation ID |
| `runner`, `machine`, `environment`, `scan_mode`, `dry_run` | Grouping dimensions; unavailable identities are null and environment identity contains no credentials |
| `started_at`, `finished_at`, `duration_seconds` | UTC timestamps and monotonic elapsed seconds |
| `status`, `exit_code` | `success` or `failure`, matching the existing process outcome |
| `discovery_complete`, `submission_complete` | Whether discovery finished and all selected case submissions have known attempted outcomes; submission is false for dry runs, and complete does not mean successful |
| `executions` | Object containing the execution counts defined below |
| `cases` | Object containing the case counts defined below |

- Counts are nonnegative integers or null when unavailable. Partial runs may report known counts but must not mark the unfinished phase complete.
- Counts and durations can be totaled within compatible groups. Never add parents to their children; repeated runs measure processing activity, not unique cases or executions.
- Missing/null counts must remain distinguishable from zero. Future consumers aggregate canonical records only, deduplicate by run ID, group compatible runs, and report missing-data coverage.
- Adding optional fields is compatible; changing field types or meanings requires a new schema version.

#### Execution counts

Count one observation per execution ID at one case path encountered in the scan scope. Filtered paths and completed snapshots that are not visited are outside the total. Each observation has exactly one final discovery outcome:

| Field | Meaning / underlying decision |
| --- | --- |
| `total` | Sum of the six outcomes below |
| `selected` | Selected for submission; currently `accepted` / `new_execution` |
| `skipped` | Already processed; currently `rejected` / `already_processed` |
| `incomplete` | Required metadata is missing |
| `invalid` | Metadata failed validation |
| `unreadable` | Files could not be accessed; currently `transient` / `OSError` |
| `deferred` | Eligible but excluded by the case limit |

```text
executions.total = selected + skipped + incomplete + invalid + unreadable + deferred
run.executions.<field> = sum(case.executions.<field>)
```

Derive reporting counts from existing final per-case decisions, not a mixture of validation/cache counters. Verify the partition without changing ingestion decisions or operational counters. Keep validation/cache statistics at DEBUG, outside primary metrics.

#### Case counts

| Field | Meaning |
| --- | --- |
| `found` | Case paths with at least one execution observation |
| `eligible` | Cases eligible for submission before applying the limit |
| `selected` | Cases selected after applying the limit |
| `deferred` | Eligible cases excluded by the limit |
| `succeeded` | Successful case-submission operations, not executions created |
| `failed` | Failed case-submission operations |
| `not_attempted` | Selected cases whose submission was not attempted |

```text
cases.eligible = cases.selected + cases.deferred
cases.selected = cases.succeeded + cases.failed + cases.not_attempted
```

These equations apply when the relevant counts are known. `found`, `eligible`, and `selected` are nested populations, not values to add together. A case may contain several execution outcomes, so execution outcomes do not partition cases.

For dry runs with completed selection, `succeeded=0`, `failed=0`, and `not_attempted=selected`. For handled early failures, use null for unavailable counts; known selected but unattempted cases remain `not_attempted`. Leave backend-created/duplicate/parser-error totals outside the initial metrics contract.

### 3. Show readable summaries and document the contract

- Generate the INFO-level readable summary and metrics record from the same run data.
- Emit one compact `case_discovered` summary per case with the execution fields above. Emit a separate `case_submission` event for each attempted case, with outcome `succeeded` or `failed`; failed submissions use ERROR. Selection is not ingestion success.
- At DEBUG, expose the underlying execution decisions with `case`, `execution_id`, `outcome`, and `reason`, using the same vocabulary as the aggregates.
- Write one labeled metric per summary line, each with the normal prefix, `RUN_SUMMARY` category, and `run_id`. Remove redundant legacy summaries rather than retaining them for compatibility.
- Group the readable summary into execution outcomes, case selection, and case submission outcomes. Indent only genuine partition children.
- Document log-level examples, metric meanings, grouping, deduplication, missing-data handling, and one sample JSON record. Do not implement the future summarization module.

Example hierarchy (fields abbreviated; full readable and JSON examples belong in `ingestion-logging.md`):

```text
INFO CONFIG run_id=r1 event=run_started scan_mode=staging dry_run=false
DEBUG EXECUTION_DETAIL run_id=r1 case=case-a execution_id=e1 outcome=selected reason=new_execution
DEBUG EXECUTION_DETAIL run_id=r1 case=case-a execution_id=e2 outcome=skipped reason=already_processed
INFO CASE_SUMMARY run_id=r1 event=case_discovered case=case-a executions.total=2 executions.selected=1 executions.skipped=1
DEBUG EXECUTION_DETAIL run_id=r1 case=case-b execution_id=e1 outcome=incomplete reason=missing_metadata
INFO CASE_SUMMARY run_id=r1 event=case_discovered case=case-b executions.total=1 executions.incomplete=1
INFO CASE_SUMMARY run_id=r1 event=case_submission case=case-a outcome=succeeded
INFO RUN_SUMMARY run_id=r1 event=run_metrics payload=<single-line JSON with run metadata, executions, and cases>
```

Every physical line receives the normal UTC timestamp/severity prefix. Actual summaries include all defined fields; readable run summaries use one metric per line. Only `run_metrics` is authoritative for aggregation.

### 4. Capture launcher failures early

- Establish launcher file logging as early as the deployment root permits, before sourcing site/API configuration or checking the interpreter. Capture subsequent stdout/stderr and the final exit status without shell tracing or credential output.
- If the root is missing or log creation fails, retain stderr and document scheduler-level capture; do not promise file logging when writing a file is impossible.
- Use separate launcher events for pre-Python failures and lock skips. Do not fabricate or duplicate Python `run_metrics`; preserve existing lock and exit behavior.
- Move output capture earlier, not operational checks. Preserve configuration precedence, credential sourcing, locks, and exit codes. Scheduler examples document logging settings only; do not change schedules or enabled environments.

### Affected files

- `backend/app/scripts/ingestion/archive_ingestor_core.py`: logging policy, run context, and JSON contract.
- `backend/app/scripts/ingestion/archive_workflow.py`: shared summary data.
- `backend/app/scripts/ingestion/{nersc_archive_ingestor,hpc_upload_archive_ingestor}.py` and `v3_data/lcrc_v3_archive_ingestor.py`: logging context and final metrics around existing paths.
- `archive_discovery.py`: final outcome counts and terminology; audit `archive_client.py` and other shared logging callers.
- `backend/app/core/logger.py` only if scoped handler support is needed.
- `backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh` and scheduler examples: early failure capture and log-level configuration.
- `docs/architecture/ingestion-logging.md`, `docs/operations/setup-ingestion-operations.md`, and the site-assets README.
- New `backend/tests/features/ingestion/test_ingestion_logging.py`; existing workflow, runner, and site-launcher tests.

## Constraints and non-goals

- No changes to ingestion selection, retries, persistence, checkpoints, API, database, frontend, or existing exit semantics.
- Reporting is observational: use existing decisions, selected candidates, and submission results. Do not modify operational counters, persisted values, or control flow to satisfy reporting equations; investigate reporting definitions if they do not reconcile.
- Preserve exception propagation, return values, execution order, and configuration precedence. Do not add network requests for reporting. Logging failures must not change ingestion outcomes.
- No new dependencies, custom severity levels, summarization module, retention, rotation, or deployment work.
- Never log credentials or credential-bearing URLs.

Assumptions: an environment variable is sufficient for invocation-time configuration; aggregation-enabled deployments use INFO or DEBUG; future daily reports group by UTC completion date.

Confirmed: archive/staging log formats may change. Existing summary scripts are work in progress, not formally deployed, and will be adapted to this PR when ready. Backward compatibility with those scripts is not required.

Risk: shared logging changes may affect diagnostics tools. Audit and test shared callers; external summary-script compatibility is not a rollout blocker for this PR.

## Acceptance criteria

- INFO hides routine detail; DEBUG retains it; invalid log levels fail clearly.
- At INFO/DEBUG, each successful or handled-failure invocation emits exactly one valid metrics record. Suppressed or missing records are not interpreted as zero activity.
- Metrics and readable summaries agree, use consistent run IDs, and contain no credentials or duplicate records.
- Execution outcomes form the defined partition, run execution totals equal case-summary sums, and case selection/submission counts satisfy the defined equations when available.
- Already-processed executions still in staging are logged as skipped, not selected. A failed submission does not change execution selection counts.
- Launcher failures are retained when file logging is available; otherwise errors remain on stderr. Launcher events do not duplicate ingestion metrics.
- A test-only consumer extracts metrics despite log prefixes, ignores noncanonical events, deduplicates run IDs, excludes dry runs, groups compatible runs, and reports correct totals and missing-data coverage.
- Candidates, underlying ingestion outcomes, persistence calls, and exit codes remain unchanged; reporting names and aggregates follow the new contract.

## Validation

After implementation:

- Test severity/filtering, configuration, handler delivery, redaction, JSON escaping/types, run IDs, and exactly-once finalization.
- Cover successful, failed, empty, dry-run, partial-submission, and handled early-failure runs; verify phase completeness and null counts.
- Verify count equations and case-to-run sums for fresh and cached discovery results, repeated archive observations, existing-only/incomplete-only cases, case limits, and unreadable files. Test processed executions remaining in staging.
- Test aggregation using duplicate, mixed-environment, partial, and noncanonical records.
- Compare INFO/DEBUG workflows for unchanged ingestion behavior. Test launcher configuration forwarding.
- Test launcher failures for missing site configuration, missing/unreadable API environment files, missing credentials, missing interpreter, and unwritable log output. Verify redaction and preserved lock/exit behavior.
- Run `make backend-test`, `git diff --check`, and `make pre-commit-run` from the repository root.
- Validate the new log contract and readable output; adapting external summary scripts is separate work and does not block this PR.
