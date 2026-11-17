#!/usr/bin/env bash
# Run a site maintenance command once and report it to scheduled job health.
#
# Usage: run_reported_job.sh <site> <job-type> <command> [args...]
#
# Live runs (DRY_RUN=false) that set SIMBOARD_JOB_ID report their start and
# finish to each API environment in SIMBOARD_ENV_FILES, a colon-separated list
# of env files. Only the report processes load the site config and env files,
# so the command never receives an API token. Reporting is best effort: a
# missing file or interpreter, or an unreachable API, is logged and never stops
# the command or changes its exit code.

warn() {
  printf '[%s] run_reported_job: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >&2
}

# Send one start or finish report to every API environment.
report_job() {
  local env_file
  local -a env_files
  IFS=: read -r -a env_files <<< "${SIMBOARD_ENV_FILES}"
  for env_file in "${env_files[@]}"; do
    [[ -n "${env_file}" ]] || continue
    if [[ ! -r "${env_file}" ]]; then
      warn "API environment not readable; skipping ${1} report: ${env_file}"
      continue
    fi
    # Silence both files: shell diagnostics can echo the token.
    (
      source "${site_config}" > /dev/null 2>&1
      source "${env_file}" > /dev/null 2>&1 || exit 1
      export MACHINE_NAME SIMBOARD_JOB_ID SIMBOARD_JOB_RUN_ID
      export SIMBOARD_JOB_STARTED_AT SIMBOARD_JOB_SCAN_MODE
      cd "${backend_dir}" && "${python_bin}" -m app.scripts.ingestion.job_health "$@"
    ) || warn "${1} report not sent: ${env_file}"
  done
}

main() {
  if (( $# < 3 )) || [[ ! $1 =~ ^[abcdefghijklmnopqrstuvwxyz0123456789_-]+$ ]]; then
    echo "Usage: $0 <site> <job-type> <command> [args...]" >&2
    return 1
  fi

  local site=$1
  SIMBOARD_JOB_SCAN_MODE=$2
  shift 2

  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  backend_dir="$(cd -- "${script_dir}/../../../../.." && pwd)"
  python_bin="${backend_dir}/.venv/bin/python"
  # The site config provides MACHINE_NAME, as it does for the launcher.
  site_config="${SIMBOARD_SITE_CONFIG:-${script_dir}/../configs/${site}.config}"

  local reporting=false
  shopt -s nocasematch
  case "${DRY_RUN:-true}" in
    0|false|no|off)
      [[ -z "${SIMBOARD_JOB_ID:-}" || -z "${SIMBOARD_ENV_FILES:-}" ]] || reporting=true
      ;;
  esac
  shopt -u nocasematch

  if [[ $reporting == true && ! -r "${site_config}" ]]; then
    warn "site configuration not readable; running without job health reports: ${site_config}"
    reporting=false
  fi
  if [[ $reporting == true ]] && ! SIMBOARD_JOB_RUN_ID="$("${python_bin}" -c 'import uuid; print(uuid.uuid4())' 2> /dev/null)"; then
    warn "${python_bin} is unavailable; running without job health reports"
    reporting=false
  fi

  if [[ $reporting == true ]]; then
    SIMBOARD_JOB_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    report_job start
  fi

  local exit_code=0
  "$@" || exit_code=$?

  # A refresh may have replaced the reporter; the new one sends the finish.
  if [[ $reporting == true ]]; then
    report_job finish --exit-code "${exit_code}"
  fi

  return "${exit_code}"
}

# Keep the call and exit on one line: Bash parses the whole line before running
# it, so it never reads this file again after a refresh replaces it.
main "$@"; exit $?
