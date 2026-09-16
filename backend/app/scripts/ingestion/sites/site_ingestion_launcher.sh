#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )) || [[ ! $1 =~ ^[a-z0-9_-]+$ ]] || [[ $2 != "archive" && $2 != "staging" ]]; then
    echo "Usage: $0 <site> <staging|archive>" >&2
    exit 1
fi

site=$1
scan_mode=$2

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
site_config="${SIMBOARD_SITE_CONFIG:-${script_dir}/${site}.config}"

if [[ ! -r "${site_config}" ]]; then
  echo "Site configuration not readable: ${site_config}" >&2
  exit 1
fi

rm -f LAUNCH_LOG
echo "" >> LAUNCH_LOG 2>&1
chgrp simboard LAUNCH_LOG
ts=`date -u +%Y%m%d_%H%M%S`
echo "$ts: DEBUG: TOPSIDE: site_config = ${site_config}" >> LAUNCH_LOG 2>&1

if [[ -n "${SIMBOARD_ROOT:-}" ]]; then
  export SIMBOARD_WORKDIR="${SIMBOARD_WORKDIR:-${SIMBOARD_ROOT}/operations}"
  export SIMBOARD_MODULES="${SIMBOARD_MODULES:-${SIMBOARD_ROOT}/repository/simboard/backend}"
fi

# Site config provides paths, runner module, and optional authentication helpers.
source "${site_config}"

if [[ -n "${SIMBOARD_ROOT:-}" ]]; then
  export SIMBOARD_WORKDIR="${SIMBOARD_WORKDIR:-${SIMBOARD_ROOT}/operations}"
  export SIMBOARD_MODULES="${SIMBOARD_MODULES:-${SIMBOARD_ROOT}/repository/simboard/backend}"
fi

# SIMBOARD_REPODIR is retained as a compatibility alias for existing site configs.
export SIMBOARD_MODULES="${SIMBOARD_MODULES:-${SIMBOARD_REPODIR:-}}"

: "${SIMBOARD_WORKDIR:?SIMBOARD_WORKDIR must be set by SIMBOARD_ROOT or the site configuration}"
: "${SIMBOARD_MODULES:?SIMBOARD_MODULES must be set by SIMBOARD_ROOT or the site configuration}"

: "${SIMBOARD_INGESTOR_MODULE:?SIMBOARD_INGESTOR_MODULE must be set by the site configuration}"

export SCAN_MODE="${scan_mode}"
ts=`date -u +%Y%m%d_%H%M%S`
echo "$ts: DEBUG: scan_mode = ${scan_mode}" >> LAUNCH_LOG 2>&1

# Site config supplies archive lower bound; callers may override it.
if [[ $scan_mode == "archive" ]]; then
  export ARCHIVE_YEAR_START="${ARCHIVE_YEAR_START:-${SIMBOARD_DEFAULT_ARCHIVE_YEAR_START:?SIMBOARD_DEFAULT_ARCHIVE_YEAR_START must be set by the site configuration}}"
fi

# Optional max cases per run, default is no limit.
export MAX_CASES_PER_RUN="${MAX_CASES_PER_RUN:-}"

# Dry runs default to read-only remote-state validation. Set
# DRY_RUN_USE_REMOTE_STATE=false for credential-free offline scanning.
dry_run_normalized="${DRY_RUN:-true}"
dry_run_normalized="${dry_run_normalized#"${dry_run_normalized%%[![:space:]]*}"}"
dry_run_normalized="${dry_run_normalized%"${dry_run_normalized##*[![:space:]]}"}"
remote_state_normalized="${DRY_RUN_USE_REMOTE_STATE:-true}"
remote_state_normalized="${remote_state_normalized#"${remote_state_normalized%%[![:space:]]*}"}"
remote_state_normalized="${remote_state_normalized%"${remote_state_normalized##*[![:space:]]}"}"

ts=`date -u +%Y%m%d_%H%M%S`
echo "$ts: DEBUG: DRY_RUN_USE_REMOTE_STATE = ${remote_state_normalized}" >> LAUNCH_LOG 2>&1

load_api_configuration() {
    : "${SIMBOARD_ENV_FILE:?SIMBOARD_ENV_FILE must be set when remote API access is enabled}"
    : "${SIMBOARD_API_TOKEN_FILE:?SIMBOARD_API_TOKEN_FILE must be set when remote API access is enabled}"
    source "${SIMBOARD_ENV_FILE}"
    source "${SIMBOARD_API_TOKEN_FILE}"
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

export PYTHON_BIN="${PYTHON_BIN:-${SIMBOARD_MODULES}/.venv/bin/python}"

if [[ ! -d "${SIMBOARD_MODULES}/.venv" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >> LAUNCH_LOG 2>&1
  echo "Run 'make install' from the repository root to create it." >> LAUNCH_LOG 2>&1
  exit 1
fi

ts="$(date -u +%Y%m%d_%H%M%S)"
LOG_FILE="${SIMBOARD_WORKDIR}/raw_logs/SBCS-${scan_mode}-${site}-${ts}.log"
printf '[%s] launcher started: site=%s scan_mode=%s dry_run=%s\n' \
  "$(date -Is)" "${site}" "${scan_mode}" "${dry_run_normalized}" >> "${LOG_FILE}"
chgrp simboard ${LOG_FILE}

LOCK_FILE="$SIMBOARD_WORKDIR/SB-${scan_mode}.lock"
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


ts="$(date -u +%Y%m%d_%H%M%S)"
echo "$ts: DEBUG: DRY_RUN = ${DRY_RUN}: Invoking ${SIMBOARD_INGESTOR_MODULE}" >> LAUNCH_LOG 2>&1
cat LAUNCH_LOG >> "$LOG_FILE"
# Run the app
cd "${SIMBOARD_MODULES}"
"${PYTHON_BIN}" -m "${SIMBOARD_INGESTOR_MODULE}" >> "$LOG_FILE" 2>&1
