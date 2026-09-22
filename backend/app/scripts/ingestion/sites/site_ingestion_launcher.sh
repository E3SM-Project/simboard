#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Command-line input
# =============================================================================
# Accept one configured site and one supported archive scan mode.
if (( $# != 2 )) || [[ ! $1 =~ ^[a-z0-9_-]+$ ]] || [[ $2 != "archive" && $2 != "staging" ]]; then
    echo "Usage: $0 <site> <staging|archive>" >&2
    exit 1
fi

site=$1
scan_mode=$2

# =============================================================================
# Site configuration and standard layout
# =============================================================================
# Load the selected site's reviewed settings, then derive all repository paths
# from the scheduler-provided standard deployment root.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
site_config="${SIMBOARD_SITE_CONFIG:-${script_dir}/configs/${site}.config}"

if [[ ! -r "${site_config}" ]]; then
  echo "Site configuration not readable: ${site_config}" >&2
  exit 1
fi

# Site config provides site-specific ingestion settings.
source "${site_config}"

# Every site uses the standard deployment layout. The scheduler supplies its
# root; site configuration does not supply alternate repository or work paths.
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set by the scheduler environment}"
SIMBOARD_WORKDIR="${SIMBOARD_ROOT}/operations"
SIMBOARD_MODULES="${SIMBOARD_ROOT}/repository/simboard/backend"

: "${SIMBOARD_INGESTOR_MODULE:?SIMBOARD_INGESTOR_MODULE must be set by the site configuration}"

# =============================================================================
# Run controls
# =============================================================================
# The command selects the scan mode. Site configuration supplies the archive
# lower bound; scheduler settings may narrow the archive scan or cap submissions.
export SCAN_MODE="${scan_mode}"

if [[ $scan_mode == "archive" ]]; then
  export ARCHIVE_YEAR_START="${ARCHIVE_YEAR_START:-${SIMBOARD_DEFAULT_ARCHIVE_YEAR_START:?SIMBOARD_DEFAULT_ARCHIVE_YEAR_START must be set by the site configuration}}"
fi

export MAX_CASES_PER_RUN="${MAX_CASES_PER_RUN:-}"

# =============================================================================
# API configuration
# =============================================================================
# Dry runs default to read-only remote-state validation. Set
# DRY_RUN_USE_REMOTE_STATE=false for credential-free offline scanning.
# Read both controls with safe defaults, then trim leading and trailing
# whitespace so scheduler values such as " false " are handled correctly below.
dry_run_normalized="${DRY_RUN:-true}"
dry_run_normalized="${dry_run_normalized#"${dry_run_normalized%%[![:space:]]*}"}"
dry_run_normalized="${dry_run_normalized%"${dry_run_normalized##*[![:space:]]}"}"
remote_state_normalized="${DRY_RUN_USE_REMOTE_STATE:-true}"
remote_state_normalized="${remote_state_normalized#"${remote_state_normalized%%[![:space:]]*}"}"
remote_state_normalized="${remote_state_normalized%"${remote_state_normalized##*[![:space:]]}"}"

load_api_configuration() {
    : "${SIMBOARD_ENV_FILE:?SIMBOARD_ENV_FILE must be set when remote API access is enabled}"
    source "${SIMBOARD_ENV_FILE}"
    : "${SIMBOARD_API_BASE_URL:?SIMBOARD_API_BASE_URL must be set when remote API access is enabled}"
    : "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN failed to be set}"
}

shopt -s nocasematch
case "${dry_run_normalized}" in
  0|false|no|off)
    load_api_configuration
    ;;
  *)
    case "${remote_state_normalized}" in
      0|false|no|off) ;;
      *) load_api_configuration ;;
    esac
    ;;
esac
shopt -u nocasematch

# =============================================================================
# Python runtime
# =============================================================================
# Run the configured module with the backend virtual environment.
export PYTHON_BIN="${PYTHON_BIN:-${SIMBOARD_MODULES}/.venv/bin/python}"

if [[ ! -d "${SIMBOARD_MODULES}/.venv" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >&2
  echo "Run 'make install' from the repository root to create it." >&2
  exit 1
fi

# =============================================================================
# Logging and concurrency
# =============================================================================
# Write one log per invocation. Jobs targeting different API environments may
# run together; staging and archive jobs for one environment share a lock.
ts="$(date -u +%Y%m%d_%H%M%S)"
LOG_FILE="${SIMBOARD_WORKDIR}/SBCS-${scan_mode}-${site}-${ts}.log"
printf '[%s] launcher started: site=%s scan_mode=%s dry_run=%s\n' \
  "$(date -Is)" "${site}" "${scan_mode}" "${dry_run_normalized}" >> "${LOG_FILE}"

environment_lock_name="${SIMBOARD_ENV_FILE:-offline}"
environment_lock_name="${environment_lock_name##*/}"
LOCK_FILE="$SIMBOARD_WORKDIR/SBCS-${site}-${environment_lock_name}.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -Is)] SKIP launch simboard collection, lock already held, pid $$" >> "$LOG_FILE"
  exit 0
fi

cleanup() {
  local exit_code=$?
  echo "[$(date -Is)] simboard collection launcher exiting, pid $$, exit_code ${exit_code}" >> "$LOG_FILE"
}
trap cleanup EXIT

# =============================================================================
# Ingestion execution
# =============================================================================
# Run the selected ingestor and append its structured events to this invocation's log.
cd "${SIMBOARD_MODULES}"
"${PYTHON_BIN}" -m "${SIMBOARD_INGESTOR_MODULE}" >> "$LOG_FILE" 2>&1
