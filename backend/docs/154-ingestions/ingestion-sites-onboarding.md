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

The repository uses a config-driven host-side launcher for site collection:

- `backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh` loads a named site config and selects its ingestion runner.
- `backend/app/scripts/ingestion/sites/chrysalis.config` and `nersc.config` provide site-specific paths, machine names, runner modules, and protected credential-file locations.
- `backend/app/scripts/ingestion/hpc_upload_archive_ingestor.py` is the scheduler-agnostic upload runner for remote HPC sites; `nersc_archive_ingestor.py` handles NERSC path ingestion.
- `backend/app/scripts/README.md` documents launcher use and site-config responsibilities.
- `backend/tests/features/ingestion/test_site_collection_launcher.py` covers config-driven offline launcher behavior.

PR 169 is an open draft for this Chrysalis work. Take it over from there rather than starting a new branch. The PR currently notes that local validation was blocked because PostgreSQL was unavailable at `127.0.0.1`, so backend tests still need to be rerun in a working local or CI environment.

The key design rule is that shell wrappers should stay thin. Put reusable ingestion behavior in Python, not in site-specific shell scripts.

## How Ingestion Works

The existing ingestor scans a performance archive directory, finds parseable execution directories, tracks state, and calls the SimBoard path-ingestion API for changed cases.

The shared entrypoint is intended to be stable across schedulers:

```bash
app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis staging
```

Site configs should set only local defaults such as:

- `MACHINE_NAME`
- `PERF_ARCHIVE_ROOT`
- `DRY_RUN`
- `DRY_RUN_USE_REMOTE_STATE`
- `SIMBOARD_INGESTOR_MODULE`
- protected environment and token file locations

For normal execution and default dry runs, the launcher loads the API environment
and token from the protected files referenced by the site config:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`

See `docs/hpc_api_token_authentication.md` for service account and API token setup.

## Chrysalis Handoff

Start with Chrysalis.

Current launcher invocation:

```bash
backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis staging
```

The Chrysalis config defaults to:

- `MACHINE_NAME=chrysalis`
- `PERF_ARCHIVE_ROOT=/lcrc/group/e3sm/PERF_Chrysalis/performance_archive`
- `DRY_RUN=true`

Set `DRY_RUN_USE_REMOTE_STATE=false` only when a credential-free offline scan is
needed; default dry runs read remote state and checkpoints without writing data.

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
6. Run the Chrysalis launcher with the default dry-run mode.
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
