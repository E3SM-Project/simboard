# Site Ingestion Onboarding

## Purpose

This work extends SimBoard metadata ingestion beyond Perlmutter/NERSC. The first target is Chrysalis because it already has a Jenkins-based PACE workflow and can use the same ingestion model with only site-specific environment defaults.

Tracking issue: https://github.com/E3SM-Project/simboard/issues/154

Takeover PR: https://github.com/E3SM-Project/simboard/pull/169

Current branch:

```bash
feature/154-ingestion-sites
```

## Current State

The branch introduces a shared HPC ingestion entrypoint and a thin Chrysalis wrapper:

- `backend/app/scripts/ingestion/hpc_archive_ingestor.py` is the scheduler-agnostic entrypoint for HPC site wrappers. It currently delegates to the existing NERSC archive ingestor so Perlmutter behavior stays unchanged.
- `backend/app/scripts/ingestion/sites/chrysalis.sh` is the Chrysalis Jenkins wrapper. It sets Chrysalis defaults, requires SimBoard API configuration from the caller, and runs the shared Python entrypoint.
- `backend/app/scripts/README.md` documents how to run the shared ingestor and how site wrappers should be structured.
- `backend/tests/features/ingestion/test_nersc_archive_ingestor.py` includes coverage for the generic entrypoint.

PR 169 is an open draft for this Chrysalis work. Take it over from there rather than starting a new branch. The PR currently notes that local validation was blocked because PostgreSQL was unavailable at `127.0.0.1`, so backend tests still need to be rerun in a working local or CI environment.

The key design rule is that shell wrappers should stay thin. Put reusable ingestion behavior in Python, not in site-specific shell scripts.

## How Ingestion Works

The existing ingestor scans a performance archive directory, finds parseable execution directories, tracks state, and calls the SimBoard path-ingestion API for changed cases.

The shared entrypoint is intended to be stable across schedulers:

```bash
uv run python -m app.scripts.ingestion.hpc_archive_ingestor
```

Site wrappers should set only local defaults such as:

- `MACHINE_NAME`
- `PERF_ARCHIVE_ROOT`
- `STATE_PATH`
- `DRY_RUN`
- `PYTHON_BIN`, when the site needs a specific Python executable

The SimBoard API target and token must be provided by the runner environment:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`

See `docs/hpc_api_token_authentication.md` for service account and API token setup.

## Chrysalis Handoff

Start with Chrysalis.

Current wrapper:

```bash
backend/app/scripts/ingestion/sites/chrysalis.sh
```

The wrapper defaults to:

- `MACHINE_NAME=chrysalis`
- `PERF_ARCHIVE_ROOT=/lcrc/group/e3sm/PERF_Chrysalis/performance_archive`
- `STATE_PATH=${PERF_ARCHIVE_ROOT}/../simboard-ingestion-state.json`
- `DRY_RUN=true`

Before enabling real ingestion, validate:

- The archive path exists and is readable from the Jenkins runtime.
- Jenkins can run the backend Python environment.
- Jenkins can inject `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` without logging the token.
- The Jenkins host has network egress to the SimBoard API.
- Dry-run output shows expected candidate counts.
- The state file location is writable and persists across runs.

Do not set `DRY_RUN=false` until the dry-run behavior has been reviewed.

## Recommended Task Order

1. Review the current branch implementation and confirm it matches the thin-wrapper design.
2. Rerun backend tests for PR 169 in an environment with PostgreSQL available.
3. Validate the Chrysalis archive path and Jenkins environment.
4. Create or identify the SimBoard service account and API token for HPC ingestion.
5. Configure Jenkins to provide `SIMBOARD_API_BASE_URL` and `SIMBOARD_API_TOKEN` securely.
6. Run the Chrysalis wrapper with the default dry-run mode.
7. Review candidate counts, skipped cases, errors, and state-file behavior.
8. Enable non-dry-run ingestion only after validation.
9. Apply the same wrapper pattern to additional sites once access is available.

## Remaining Sites

Priority and status from issue discussion:

- Chrysalis: first target; Jenkins workflow.
- Frontier: request or confirm account access.
- Aurora: request or confirm account access.
- Compy: request or confirm account access.
- Anvil: removed from scope.

Expected runners from the PACE references:

- Chrysalis and Compy use Jenkins.
- Frontier uses cron.
- Aurora uses ALCF GitLab.

Confirm these runner assumptions before implementing wrappers for non-Chrysalis sites.

## References

- Issue 154: https://github.com/E3SM-Project/simboard/issues/154
- PR 169: https://github.com/E3SM-Project/simboard/pull/169
- PACE overview: https://e3sm.atlassian.net/wiki/spaces/EPG/pages/776437853/Performance+Analytics+for+Computational+Experiments+PACE
- PACE collection/upload reference: https://e3sm.atlassian.net/wiki/spaces/EPG/pages/5477335106/PACE+Collection+and+Upload+Reference
- Existing site script wrappers: https://github.com/E3SM-Project/E3SM_test_scripts/tree/master/jenkins
- Existing PACE archive script: https://github.com/E3SM-Project/E3SM_test_scripts/blob/master/util/pace_archive.sh
- SimBoard script docs: `backend/app/scripts/README.md`
- API token docs: `docs/hpc_api_token_authentication.md`
