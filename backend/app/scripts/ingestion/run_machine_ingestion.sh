#!/usr/bin/env bash
# Make entry point. Keep site scheduler invocations backward compatible.
set -euo pipefail

fail() { printf '%s\n' "$1" >&2; exit 1; }
[[ $# == 1 && ( $1 == true || $1 == false ) ]] || fail 'Expected dry-run mode: true or false'
requested_dry_run=$1
case "${machine:-}" in
  chrysalis|perlmutter) selected_machine=$machine ;;
  *) fail 'machine must be chrysalis or perlmutter' ;;
esac
[[ ${env:-} == dev || ${env:-} == prod ]] || fail 'env must be dev or prod'
selected_scan_mode=${scan_mode:-}
[[ $selected_scan_mode == archive || $selected_scan_mode == staging ]] || fail 'scan_mode must be archive or staging (required)'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config="$script_dir/sites/configs/$selected_machine.config"
[[ -r $config ]] || fail "Machine configuration not readable: $config"
export DRY_RUN=$requested_dry_run
export PYTHONUNBUFFERED=1
export SIMBOARD_ENV_FILE=${env_file:-}
if [[ $selected_machine == chrysalis ]]; then
  [[ -n ${SIMBOARD_ROOT:-} ]] || fail 'SIMBOARD_ROOT must be set for chrysalis'
  export SIMBOARD_ENV_FILE=${env_file:-${SIMBOARD_ROOT}/operations/env.${env}.sh}
  export SIMBOARD_SITE_CONFIG=$config
  export SIMBOARD_ENFORCE_RUN_CONTROLS=true
  export SIMBOARD_CONSOLE_LOG=true
  exec bash "$script_dir/sites/site_ingestion_launcher.sh" "$selected_machine" "$selected_scan_mode"
fi

# Export assignments from protected files, without leaking shell diagnostics.
if [[ -n $SIMBOARD_ENV_FILE ]]; then
  [[ -f $SIMBOARD_ENV_FILE && -r $SIMBOARD_ENV_FILE ]] || fail "API environment file not readable: $SIMBOARD_ENV_FILE"
  set -a
  exec 3>&2
  trap 'printf "%s\n" "Failed to load API environment file" >&3' ERR
  # shellcheck source=/dev/null
  source "$SIMBOARD_ENV_FILE" > /dev/null 2>&1
  trap - ERR
  exec 3>&-
  set +a
fi
# shellcheck source=/dev/null
source "$config"
export DRY_RUN=$requested_dry_run SCAN_MODE=$selected_scan_mode
if [[ $SCAN_MODE == archive ]]; then
  export ARCHIVE_YEAR_START=${ARCHIVE_YEAR_START:-$SIMBOARD_DEFAULT_ARCHIVE_YEAR_START}
fi
remote_state_normalized=${DRY_RUN_USE_REMOTE_STATE:-true}
remote_state_normalized="${remote_state_normalized#"${remote_state_normalized%%[![:space:]]*}"}"
remote_state_normalized="${remote_state_normalized%"${remote_state_normalized##*[![:space:]]}"}"
case "$remote_state_normalized" in
  [Ff][Aa][Ll][Ss][Ee]|0|[Nn][Oo]|[Oo][Ff][Ff]) remote_state=false ;;
  *) remote_state=true ;;
esac
if [[ $DRY_RUN == false || $remote_state == true ]]; then
  [[ -n ${SIMBOARD_API_BASE_URL:-} ]] || fail 'SIMBOARD_API_BASE_URL must be set for remote API access'
  [[ -n ${SIMBOARD_API_TOKEN:-} ]] || fail 'SIMBOARD_API_TOKEN must be set for remote API access'
fi
backend_dir="$(cd -- "$script_dir/../../.." && pwd)"
python_bin=${PYTHON_BIN:-$backend_dir/.venv/bin/python}
[[ -x $python_bin ]] || fail "Expected Python interpreter at $python_bin; run make backend-install"
cd "$backend_dir"
exec "$python_bin" -m "$SIMBOARD_INGESTOR_MODULE"
