#!/usr/bin/env bash
set -euo pipefail
umask 027

finish_logging() {
  local exit_code=$?
  printf '[%s] event=launcher_finished exit_code=%s\n' "$(date -u -Is)" "$exit_code" >&"$log_output_fd" || true
  # Do not wait for tee here: a failing source command may still hold saved
  # output descriptors until the shell exits, preventing tee from seeing EOF.
  exit "$exit_code"
}

start_logging() {
  if [[ ${SIMBOARD_CONSOLE_LOG:-false} == true ]]; then
    printf 'Ingestion log: %s\n' "$LOG_FILE"
    # Keep writing the file if a console pipe closes (GNU tee's pipe mode).
    exec > >(tee -p -a "$LOG_FILE") 2>&1
  else
    exec >> "$LOG_FILE" 2>&1
  fi
  # Keep the completion event visible even when source diagnostics are muted.
  exec {log_output_fd}>&1
  trap finish_logging EXIT
}

# Capture failures before configuration is sourced or Python is checked. If the
# deployment root/log directory is unavailable, stderr remains scheduler-owned.
if [[ -n "${SIMBOARD_ROOT:-}" ]]; then
  early_log_dir="${SIMBOARD_ROOT}/operations/raw_logs"
  if mkdir -p -m 750 "${early_log_dir}"; then
    early_environment="${SIMBOARD_ENV_FILE:-offline}"
    early_environment="${early_environment##*/}"
    early_site="${1:-unknown}"
    early_mode="${2:-unknown}"
    [[ "${early_site}" =~ ^[a-z0-9_-]+$ ]] || early_site=unknown
    [[ "${early_mode}" == staging || "${early_mode}" == archive || "${early_mode}" == diagnostics ]] || early_mode=unknown
    early_log_prefix="simboard-ingestion-${early_mode}"
    if [[ "${early_mode}" == diagnostics ]]; then
      early_log_prefix="simboard-diagnostics"
    fi
    early_environment="${early_environment//[^a-zA-Z0-9._-]/_}"
    LOG_FILE="${early_log_dir}/${early_log_prefix}-${early_site}-${early_environment}-$(date -u +%Y%m%d_%H%M%S)-$$.log"
    if touch "${LOG_FILE}"; then
      start_logging
      printf '[%s] event=launcher_started\n' "$(date -u -Is)"
    else
      unset LOG_FILE
    fi
  fi
fi

# =============================================================================
# Command-line input
# =============================================================================
# Accept one configured site and one supported operation.
if (( $# != 2 )) || [[ ! $1 =~ ^[a-z0-9_-]+$ ]] || [[ $2 != "archive" && $2 != "staging" && $2 != "diagnostics" ]]; then
    echo "Usage: $0 <site> <staging|archive|diagnostics>" >&2
    exit 1
fi

site=$1
scan_mode=$2
requested_dry_run="${DRY_RUN:-true}"

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

# Site config provides the machine identity and ingestion settings.
source "${site_config}"
if [[ ${SIMBOARD_ENFORCE_RUN_CONTROLS:-false} == true ]]; then
  export DRY_RUN="${requested_dry_run}"
fi

# Every site uses the standard deployment layout. The scheduler supplies its
# root; site configuration does not supply alternate repository or work paths.
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set by the scheduler environment}"
SIMBOARD_WORKDIR="${SIMBOARD_ROOT}/operations"
SIMBOARD_MODULES="${SIMBOARD_ROOT}/repository/simboard/backend"
SIMBOARD_RAW_LOG_DIR="${SIMBOARD_WORKDIR}/raw_logs"

# =============================================================================
# Operation configuration
# =============================================================================
if [[ $scan_mode == "diagnostics" ]]; then
  module="app.scripts.ingestion.diagnostics_link_scanner"
  log_prefix="simboard-diagnostics"
  task_label="diagnostics"
  module_label="scanner"
else
  : "${SIMBOARD_INGESTOR_MODULE:?SIMBOARD_INGESTOR_MODULE must be set by the site configuration}"
  module="${SIMBOARD_INGESTOR_MODULE}"
  log_prefix="simboard-ingestion-${scan_mode}"
  task_label="ingestion"
  module_label="ingestor"
  export SCAN_MODE="${scan_mode}"
  export MAX_CASES_PER_RUN="${MAX_CASES_PER_RUN:-}"
  if [[ $scan_mode == "archive" ]]; then
    export ARCHIVE_YEAR_START="${ARCHIVE_YEAR_START:-${SIMBOARD_DEFAULT_ARCHIVE_YEAR_START:?SIMBOARD_DEFAULT_ARCHIVE_YEAR_START must be set by the site configuration}}"
  fi
fi

# =============================================================================
# API configuration
# =============================================================================
# Trim scheduler values before deciding whether API access is needed.
dry_run_normalized="${DRY_RUN:-true}"
dry_run_normalized="${dry_run_normalized#"${dry_run_normalized%%[![:space:]]*}"}"
dry_run_normalized="${dry_run_normalized%"${dry_run_normalized##*[![:space:]]}"}"
remote_state_normalized="${DRY_RUN_USE_REMOTE_STATE:-true}"
remote_state_normalized="${remote_state_normalized#"${remote_state_normalized%%[![:space:]]*}"}"
remote_state_normalized="${remote_state_normalized%"${remote_state_normalized##*[![:space:]]}"}"

load_api_configuration() {
    : "${SIMBOARD_ENV_FILE:?SIMBOARD_ENV_FILE must be set when remote API access is enabled}"
    # Malformed assignments can echo tokens in shell diagnostics. Preserve
    # source/errexit semantics, but retain only the phase and final exit status.
    printf '[%s] event=launcher_loading_api_environment\n' "$(date -u -Is)"
    if [[ ! -r "${SIMBOARD_ENV_FILE}" ]]; then
      printf '[%s] event=launcher_api_environment_unreadable\n' "$(date -u -Is)" >&2
    fi
    source "${SIMBOARD_ENV_FILE}" > /dev/null 2>&1
    : "${SIMBOARD_API_BASE_URL:?SIMBOARD_API_BASE_URL must be set when remote API access is enabled}"
    : "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN failed to be set}"
}

shopt -s nocasematch
if [[ $scan_mode == "diagnostics" ]]; then
  # Diagnostics dry runs are offline; export a canonical boolean for Python.
  case "${dry_run_normalized}" in
    0|false|no|off)
      load_api_configuration
      export DRY_RUN=false
      ;;
    1|true|yes|on)
      export DRY_RUN=true
      ;;
    *)
      echo "DRY_RUN must be a boolean" >&2
      exit 1
      ;;
  esac
else
  # Ingestion dry runs read remote state unless explicitly configured offline.
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
fi
shopt -u nocasematch
if [[ ${SIMBOARD_ENFORCE_RUN_CONTROLS:-false} == true ]]; then
  export DRY_RUN="${requested_dry_run}" SCAN_MODE="${scan_mode}"
fi

# =============================================================================
# Python runtime
# =============================================================================
# Run the configured module with the backend virtual environment.
export PYTHON_BIN="${PYTHON_BIN:-${SIMBOARD_MODULES}/.venv/bin/python}"

if [[ ! -d "${SIMBOARD_MODULES}/.venv" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >&2
  echo "Run 'make backend-install' from the repository root to create it." >&2
  exit 1
fi

# =============================================================================
# Logging and concurrency
# =============================================================================
# Write one log per invocation. Jobs targeting different API environments may
# run together, so include the environment name in the log filename. Staging
# and archive jobs use separate locks, while runs of the same mode share one.
environment_lock_name="${SIMBOARD_ENV_FILE:-offline}"
environment_lock_name="${environment_lock_name##*/}"
mkdir -p -m 750 "${SIMBOARD_RAW_LOG_DIR}"
if [[ -z "${LOG_FILE:-}" ]]; then
  LOG_FILE="${SIMBOARD_RAW_LOG_DIR}/${log_prefix}-${site}-${environment_lock_name}-$(date -u +%Y%m%d_%H%M%S)-$$.log"
  start_logging
fi
printf '[%s] launcher started: site=%s scan_mode=%s dry_run=%s\n' \
  "$(date -Is)" "${site}" "${scan_mode}" "${dry_run_normalized}"
if [[ $scan_mode == "diagnostics" ]]; then
  printf '[%s] launcher configuration: site_config=%s scanner_module=%s\n' \
    "$(date -Is)" "${site_config}" "${module}"
else
  printf '[%s] launcher configuration: site_config=%s dry_run_use_remote_state=%s ingestor_module=%s\n' \
    "$(date -Is)" "${site_config}" "${remote_state_normalized}" "${module}"
fi

LOCK_FILE="$SIMBOARD_WORKDIR/${log_prefix}-${site}-${environment_lock_name}.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -Is)] lock already held; ${task_label} was not started, pid $$"
  if [[ "${scan_mode}" != "staging" ]]; then
    exit 1
  fi
  exit 0
fi

# Existing deployments leave their legacy lock files behind. Hold one when it
# exists so a newly deployed launcher cannot overlap an in-flight old launcher.
legacy_lock_file="$SIMBOARD_WORKDIR/SBCS-${site}-${environment_lock_name}.lock"
if [[ $scan_mode != "diagnostics" && -e "${legacy_lock_file}" ]]; then
  exec 201>"$legacy_lock_file"
  if ! flock -n 201; then
    echo "[$(date -Is)] legacy lock already held; ingestion was not started, pid $$"
    if [[ "${scan_mode}" == "archive" ]]; then
      exit 1
    fi
    exit 0
  fi
fi

# =============================================================================
# Module execution
# =============================================================================
# Run the selected module and append its structured events to this invocation's log.
cd "${SIMBOARD_MODULES}"
printf '[%s] invoking %s: module=%s\n' \
  "$(date -Is)" "${module_label}" "${module}"
"${PYTHON_BIN}" -m "${module}" {log_output_fd}>&-
