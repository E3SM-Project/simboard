# Setup for Collection Scripts and Crontab

## Enables

- standardized routine remote site metadata collection for Simboard backend ingestion

## Important Locations

```text
[SIMBOARD_ROOT]/                        User/Operator-selected read/write/execute directory
[SIMBOARD_ROOT]/repository/simboard     Location of git-cloned "simboard" repository 
[SIMBOARD_ROOT]/operations              Initial work directory for crontab execution, overflow logs, notes
```

## Important Files

```text
[SIMBOARD_ROOT]/repository/simboard/backend/app/scripts/ingestion/sites/<site>.config

    These are the site-specific environment variables the site-launch script will export.

[SIMBOARD_ROOT]/operations/.api_token_export

    Holds the export command that will set the SIMBOARD_API_TOKEN variable when sourced in
    the cron'd site_ingestion_launcher.sh script. This adds a layer of indirection to prevent
    accidental storage of the token in the public repository.
```

## Procedures

Assuming the "SIMBOARD_ROOT", repository and operations directories are set, and the
site configuration file is properly defined in 

    [SIMBOARD_ROOT]/repository/simboard/backend/app/scripts/ingestion/sites/<site>.config

the following command line, established in your crontab file, will serve to run the background
collection in "staging" or "archive" modes, respectively:

```text
    export SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
        && cd ${SIMBOARD_ROOT}/operations \
        && ${SIMBOARD_ROOT}/repository/simboard/backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis staging 

    export SIMBOARD_ROOT=/lcrc/group/e3sm2/simboard \
        && cd ${SIMBOARD_ROOT}/operations \
        && ${SIMBOARD_ROOT}/repository/simboard/backend/app/scripts/ingestion/sites/site_ingestion_launcher.sh chrysalis archive 
```

## About the Site Config

The following sample (from Chrysalis) demonstrates certain flexibilities involved:

```text
    # export SIMBOARD_WORKDIR="/lcrc/group/e3sm2/simboard/operations"
    # export SIMBOARD_MODULES="/lcrc/group/e3sm2/simboard/repository/simboard/backend"
    export SIMBOARD_ENV_FILE="${HOME}/envs/test_simboard/bin/activate"
    export SIMBOARD_API_TOKEN_FILE="${SIMBOARD_WORKDIR}/.api_token_export"
    export SIMBOARD_INGESTOR_MODULE="app.scripts.ingestion.hpc_upload_archive_ingestor"
    export SIMBOARD_API_BASE_URL="${SIMBOARD_API_BASE_URL:-https://simboard-dev-api.e3sm.org}"
    export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START="${SIMBOARD_DEFAULT_ARCHIVE_YEAR_START:-2025-01}"
    export DRY_RUN="${DRY_RUN:-true}"
    export PERF_ARCHIVE_ROOT="${PERF_ARCHIVE_ROOT:-/lcrc/group/e3sm/PERF_Chrysalis/performance_archive}"
    export OLD_PERF_ARCHIVE_ROOT="${OLD_PERF_ARCHIVE_ROOT:-/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF}"
    export MACHINE_NAME="${MACHINE_NAME:-chrysalis}"
```

Note that the first two variables (SIMBOARD_WORKDIR, SIMBOARD_MODULES) can be set automatically in 
the launcher script, defined by their relation to SIMBOARD_ROOT.  Likewise, we could eliminate
SIMBOARD_INGESTOR_MODULE, as this fixed string is not site-dependent and could be defined in the
laucher script.  The same is true for SIMBOARD_API_BASE_URL, and although MACHINE_NAME is site
specific, it is supplied on the crontab command line and could be exported in the launch script.

Hence, the minimal site configuration script might look like:

```text
    export SIMBOARD_ENV_FILE="${HOME}/envs/test_simboard/bin/activate"
    export SIMBOARD_API_TOKEN_FILE="${SIMBOARD_WORKDIR}/.api_token_export"
    export SIMBOARD_API_BASE_URL="${SIMBOARD_API_BASE_URL:-https://simboard-dev-api.e3sm.org}"
    export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START="${SIMBOARD_DEFAULT_ARCHIVE_YEAR_START:-2025-01}"
    export DRY_RUN="${DRY_RUN:-true}"
    export PERF_ARCHIVE_ROOT="${PERF_ARCHIVE_ROOT:-/lcrc/group/e3sm/PERF_Chrysalis/performance_archive}"
    export OLD_PERF_ARCHIVE_ROOT="${OLD_PERF_ARCHIVE_ROOT:-/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF}"
```

