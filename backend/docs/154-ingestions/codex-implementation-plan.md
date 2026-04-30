# Chrysalis-First SimBoard HPC Ingestion Plan

## Executive Summary

Extend SimBoard metadata ingestion beyond Perlmutter/NERSC with one reusable
HPC ingestion framework and thin per-site adapters. Do not create separate
one-off implementations per site, and do not copy the NERSC Spin deployment
pattern unchanged.

Chrysalis is the priority implementation target. It has the clearest current
path because the PACE reference and the existing GitHub script both indicate a
Sandia Jenkins workflow and a known archive root.

Hold off on Compy, Aurora, and Frontier implementation until accounts or
equivalent native-runner access exist. Without access, implementation cannot
validate archive paths, scheduler behavior, token storage, network egress, or
metadata layout. These sites remain documented as future candidates only.

Primary source: `/Users/vo13/Downloads/EPG-PACE Collection and Upload Reference-280426-174740.pdf`.

Supporting GitHub sources:

- `https://github.com/E3SM-Project/E3SM_test_scripts/blob/master/jenkins/chrysalis_pace.sh`
- `https://github.com/E3SM-Project/E3SM_test_scripts/blob/master/jenkins/compy_pace.sh`
- `https://github.com/E3SM-Project/E3SM_test_scripts/blob/master/util/pace_archive.sh`

## Current State By Site

| Site | Current state from source materials | SimBoard plan |
| --- | --- | --- |
| Perlmutter | Already implemented through NERSC Spin CronJob against NERSC-mounted archive storage. | Keep existing deployment. Use as reference for scanner, state, retry, dry-run, and logging behavior. |
| Chrysalis | PACE PDF and `chrysalis_pace.sh` show Sandia Jenkins and `/lcrc/group/e3sm/PERF_Chrysalis/performance_archive`. | Priority site. Add thin SimBoard shell wrapper for Jenkins and run shared Python ingestor. |
| Compy | PACE PDF and `compy_pace.sh` show Sandia Jenkins and `/compyfs/performance_archive`. | Defer until Compy account or native Jenkins validation exists. |
| Aurora | PACE PDF shows ALCF GitLab scheduled daily job and `/lus/flare/projects/E3SM_Dec/performance_archive`. | Defer until ALCF account/native-runner access exists. Do not force Jenkins. |
| Frontier | PACE PDF shows `/lustre/orion/proj-shared/cli115` and local cron/unknown frequency. | Defer until OLCF account, owner, runner, and script details are confirmed. |

## Common Architecture Recommendation

Use this common flow for all supported sites:

```text
site scheduler -> thin SimBoard .sh wrapper -> shared Python ingestor -> SimBoard API
```

Thin site wrappers should live in SimBoard because SimBoard owns the API
contract, runtime environment variables, and ingestion behavior. Wrappers should
only:

- load site-specific modules or Python environment when needed
- set `MACHINE_NAME`
- set `PERF_ARCHIVE_ROOT`
- set `STATE_PATH`
- require `SIMBOARD_API_BASE_URL`
- require `SIMBOARD_API_TOKEN`
- call `python -m app.scripts.ingestion.hpc_archive_ingestor`

The shared Python ingestor should own:

- archive scanning
- metadata validation
- idempotent state tracking
- dry-run behavior
- retry/backoff
- structured logs
- SimBoard API submission

## Shared Components Vs Site-Specific Components

Standardize these parts:

- scan and parseable execution discovery
- metadata validation using existing SimBoard parser behavior
- state-file deduplication
- dry-run and capped-ingest controls
- retry/backoff and deterministic non-zero failure exits
- service-account token authentication
- structured startup, scan, candidate, success, failure, and summary logs

Keep these parts site-specific:

- scheduler: Jenkins, GitLab, cron, or site-native runner
- module/Python setup
- archive root and state path
- secret storage and token rotation workflow
- network/proxy/egress setup
- local filesystem permissions

## Execution Model By Site

| Site | Execution model |
| --- | --- |
| Perlmutter | Existing NERSC Spin CronJob. |
| Chrysalis | Sandia Jenkins wrapper. |
| Compy | Sandia Jenkins later, after account/native-runner validation. |
| Aurora | ALCF GitLab later, after ALCF access validation. |
| Frontier | Local cron or OLCF-native runner later, after owner/runtime confirmation. |

## Reuse And Generalization Guidance

Generalize the current NERSC ingestor by reusing its durable behavior:

- archive scan
- execution-dir validation
- idempotent state
- dry-run mode
- retry/backoff
- structured logging

Do not generalize by hardcoding NERSC assumptions:

- no Perlmutter default in site wrappers
- no assumption that SimBoard can mount every remote DOE filesystem
- no assumption that every site uses NERSC Spin CronJob
- no single shared token across sites

For Chrysalis, start with path-based ingestion only if the runtime can present a
path readable by the SimBoard ingestion API. If the SimBoard backend cannot read
the site filesystem, switch that site to upload-mode ingestion after access and
sample data validation.

## Recommended Rollout Order

1. Confirm with @rljacob that Chrysalis is the highest-value first site.
2. Preserve current Perlmutter/NERSC behavior.
3. Add generic `hpc_archive_ingestor` entrypoint that delegates to existing
   scanner/state/retry/logging logic.
4. Add Chrysalis Jenkins wrapper.
5. Validate Chrysalis with dry-run and capped ingest.
6. Move Chrysalis to scheduled Jenkins only after state, counts, failure status,
   token storage, and logs are verified.
7. Re-rank Compy, Aurora, and Frontier after accounts or native-runner access
   are available.

## Risks, Unknowns, And Assumptions

Risks and unknowns:

- Compy, Aurora, and Frontier cannot be safely implemented without access.
- Remote DOE filesystems may not be readable from the SimBoard backend.
- Non-NERSC sites may require upload-mode ingestion rather than path-mode
  ingestion.
- Site egress to SimBoard may require proxy or firewall changes.
- Token storage and rotation are site-specific operational concerns.
- Existing PACE cleanup removes files larger than 50 MB; confirm this does not
  remove metadata required by SimBoard.

Assumptions:

- Anvil is out of scope for this plan.
- Existing SimBoard `/ingestions/from-path` and `/ingestions/from-upload` APIs
  are sufficient for initial rollout planning.
- One service-account token should be provisioned per site.
- Existing PACE scripts remain responsible for PACE collection/upload. SimBoard
  wrappers only bridge archived metadata into SimBoard.

## Concrete Next Steps

1. Ask @rljacob to confirm Chrysalis as first priority.
2. Confirm Chrysalis Jenkins owner, token storage mechanism, and service account
   rotation path.
3. Confirm Chrysalis archive root:
   `/lcrc/group/e3sm/PERF_Chrysalis/performance_archive`.
4. Get one recent Chrysalis archived case path.
5. Run Chrysalis dry-run with `DRY_RUN=true`.
6. Run capped ingest with `MAX_CASES_PER_RUN`.
7. Verify SimBoard created/duplicate/error counts.
8. Verify state file prevents repeat ingestion.
9. Verify Jenkins marks ingestion failures as failed jobs.
