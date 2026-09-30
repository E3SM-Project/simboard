#!/usr/bin/env bash
set -euo pipefail
umask 027

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
    [[ "${early_mode}" == staging || "${early_mode}" == archive ]] || early_mode=unknown
    early_environment="${early_environment//[^a-zA-Z0-9._-]/_}"
    LOG_FILE="${early_log_dir}/simboard-ingestion-${early_mode}-${early_site}-${early_environment}-$(date -u +%Y%m%d_%H%M%S)-$$.log"
    if touch "${LOG_FILE}"; then
      exec >> "${LOG_FILE}" 2>&1
      trap 'exit_code=$?; printf "[%s] event=launcher_finished exit_code=%s\n" "$(date -u -Is)" "$exit_code" >> "${LOG_FILE}"' EXIT
      printf '[%s] event=launcher_started\n' "$(date -u -Is)"
    else
      unset LOG_FILE
    fi
  fi
fi

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
SIMBOARD_RAW_LOG_DIR="${SIMBOARD_WORKDIR}/raw_logs"

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
  LOG_FILE="${SIMBOARD_RAW_LOG_DIR}/simboard-ingestion-${scan_mode}-${site}-${environment_lock_name}-$(date -u +%Y%m%d_%H%M%S)-$$.log"
  exec >> "${LOG_FILE}" 2>&1
  trap 'exit_code=$?; printf "[%s] event=launcher_finished exit_code=%s\n" "$(date -u -Is)" "$exit_code" >> "${LOG_FILE}"' EXIT
fi
printf '[%s] launcher started: site=%s scan_mode=%s dry_run=%s\n' \
  "$(date -Is)" "${site}" "${scan_mode}" "${dry_run_normalized}" >> "${LOG_FILE}"
printf '[%s] launcher configuration: site_config=%s dry_run_use_remote_state=%s ingestor_module=%s\n' \
  "$(date -Is)" "${site_config}" "${remote_state_normalized}" "${SIMBOARD_INGESTOR_MODULE}" >> "${LOG_FILE}"

LOCK_FILE="$SIMBOARD_WORKDIR/simboard-ingestion-${scan_mode}-${site}-${environment_lock_name}.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -Is)] lock already held; ingestion was not started, pid $$" >> "$LOG_FILE"
  if [[ "${scan_mode}" == "archive" ]]; then
    exit 1
  fi
  exit 0
fi

# Existing deployments leave their legacy lock files behind. Hold one when it
# exists so a newly deployed launcher cannot overlap an in-flight old launcher.
legacy_lock_file="$SIMBOARD_WORKDIR/SBCS-${site}-${environment_lock_name}.lock"
if [[ -e "${legacy_lock_file}" ]]; then
  exec 201>"$legacy_lock_file"
  if ! flock -n 201; then
    echo "[$(date -Is)] legacy lock already held; ingestion was not started, pid $$" >> "$LOG_FILE"
    if [[ "${scan_mode}" == "archive" ]]; then
      exit 1
    fi
    exit 0
  fi
fi

# =============================================================================
# Ingestion execution
# =============================================================================
# Run the selected ingestor and append its structured events to this invocation's log.
cd "${SIMBOARD_MODULES}"
printf '[%s] invoking ingestor: module=%s\n' \
  "$(date -Is)" "${SIMBOARD_INGESTOR_MODULE}" >> "${LOG_FILE}"
"${PYTHON_BIN}" -m "${SIMBOARD_INGESTOR_MODULE}" >> "$LOG_FILE" 2>&1
