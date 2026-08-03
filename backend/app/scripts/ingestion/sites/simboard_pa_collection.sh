#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 )) || [[ $1 != "archive" && $1 != "staging" ]]; then
    echo "[$(date -Is)] ERROR: Must indicate \"staging\" or \"archive\" on the command line"
    exit 1
fi

scan_mode=$1
export SCAN_MODE="$scan_mode"

if [[ $scan_mode == "archive" ]]; then
  export ARCHIVE_YEAR_START="${ARCHIVE_YEAR_START:-2025-01}"
fi

export MAX_CASES_PER_RUN=50

# Obtain user's gimboard github repository, operations directory, and work environment:
#  (SIMBOARD_REPODIR, SIMBOARD_WORKDIR, SIMBOARD_ENV_CMD, SIMBOARD_API_TOKEN_CMD, )
site_config=$HOME/.simboard.config
source $site_config
echo "Issuing SIMBOARD_ENV_CMD = $SIMBOARD_ENV_CMD"
$SIMBOARD_ENV_CMD
export SIMBOARD_API_BASE_URL="https://simboard-dev-api.e3sm.org"

source $SIMBOARD_API_TOKEN_CMD
: "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN failed to be set.}"

export PYTHON_BIN="${PYTHON_BIN:-${SIMBOARD_REPODIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >&2
  echo "Run 'make install' from the repository root to create it." >&2
  exit 1
fi

LOCK_FILE="$SIMBOARD_WORKDIR/SBCS.lock"
ts=`date -u +%Y%m%d_%H%M%S`
LOG_FILE="$SIMBOARD_WORKDIR/SBCS-$ts.log"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -Is)] SKIP launch simboard collection, lock already held, pid $$" >> "$LOG_FILE"
  exit 0
fi

cleanup() {
  echo "[$(date -Is)] simboard collection launcher exiting, pid $$" >> "$LOG_FILE"
}
trap cleanup EXIT

# Run the app
cd "${SIMBOARD_REPODIR}"
exec "${PYTHON_BIN}" -m app.scripts.ingestion.hpc_upload_archive_ingestor >> "$LOG_FILE" 2>&1
