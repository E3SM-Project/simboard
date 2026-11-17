#!/usr/bin/env bash
# Run a site maintenance command and report it to the scheduled job health API.
#
# Usage: run_reported_job.sh <site> <job-type> <command> [args...]
#
# Live runs (DRY_RUN=false) that set SIMBOARD_JOB_ID report their start and
# finish to the API environment in SIMBOARD_ENV_FILE. The command never
# receives the API token. Reporting is best effort:
# a missing site config, API environment, or interpreter never stops the
# command or changes its exit code.

if (( $# < 3 )) || [[ ! $1 =~ ^[abcdefghijklmnopqrstuvwxyz0123456789_-]+$ ]]; then
  echo "Usage: $0 <site> <job-type> <command> [args...]" >&2
  exit 1
fi

site=$1
export SIMBOARD_JOB_SCAN_MODE=$2
shift 2

warn() {
  printf '[%s] run_reported_job: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(cd -- "${script_dir}/../../../../.." && pwd)"
python_bin="${backend_dir}/.venv/bin/python"

# The site config provides MACHINE_NAME, as it does for the launcher.
site_config="${SIMBOARD_SITE_CONFIG:-${script_dir}/../configs/${site}.config}"
if [[ -r "${site_config}" ]]; then
  # shellcheck source=/dev/null
  source "${site_config}" || warn "site configuration failed to load: ${site_config}"
else
  warn "site configuration not readable: ${site_config}"
fi

# Silence the API environment: shell diagnostics can echo the token.
if [[ -n "${SIMBOARD_ENV_FILE:-}" ]]; then
  # shellcheck source=/dev/null
  source "${SIMBOARD_ENV_FILE}" > /dev/null 2>&1 || warn "API environment failed to load"
fi

# A refresh repairs a broken backend environment, so run unreported without it.
reporter=app.scripts.ingestion.job_health
if ! cd "${backend_dir}" || ! "${python_bin}" -c "import ${reporter}" > /dev/null 2>&1; then
  warn "${python_bin} cannot load the reporter; running without job health reports"
  unset SIMBOARD_API_TOKEN
  exec "$@"
fi

# Exec so Bash stops reading this file before a refresh can replace it.
exec "${python_bin}" -m "${reporter}" exec -- "$@"
