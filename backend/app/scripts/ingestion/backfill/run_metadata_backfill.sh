#!/usr/bin/env bash
# Load existing operations credentials and site defaults for metadata-only work.
set +x +v
set -euo pipefail

fail() { printf '%s\n' "$1" >&2; exit 1; }
case "${machine:-}" in
  chrysalis|perlmutter) selected_machine=$machine ;;
  *) fail 'machine must be chrysalis or perlmutter' ;;
esac
[[ ${env:-} == dev || ${env:-} == prod ]] || fail 'env must be dev or prod'
for argument in "$@"; do
  case "$argument" in
    --machine|--machine=*) fail 'Use machine=<machine> instead of --machine in args' ;;
  esac
done

environment=${env_file:-}
if [[ -z $environment ]]; then
  [[ -n ${SIMBOARD_ROOT:-} ]] || fail 'SIMBOARD_ROOT must be set when env_file is absent'
  environment="${SIMBOARD_ROOT}/operations/env.${env}.sh"
fi
[[ -f $environment && -r $environment ]] || fail 'API environment file is missing or unreadable'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config="$script_dir/../sites/configs/$selected_machine.config"
[[ -r $config ]] || fail "Machine configuration not readable: $config"

# Do not reuse stale credentials from another deployment in the caller's shell.
unset SIMBOARD_API_BASE_URL SIMBOARD_API_TOKEN
set -a
exec 3>&2
trap 'printf "%s\n" "Failed to load API environment file" >&3; exit 1' EXIT
# shellcheck source=/dev/null
source "$environment" > /dev/null 2>&1
set +x +v > /dev/null 2>&1
trap - EXIT
exec 3>&-
set +a

export MACHINE_NAME=$selected_machine
# shellcheck source=/dev/null
source "$config"
export MACHINE_NAME=$selected_machine
[[ -n ${SIMBOARD_API_BASE_URL:-} ]] || fail 'SIMBOARD_API_BASE_URL must be set in the API environment file'
[[ -n ${SIMBOARD_API_TOKEN:-} ]] || fail 'SIMBOARD_API_TOKEN must be set in the API environment file'

backend_dir="$(cd -- "$script_dir/../../../.." && pwd)"
python_bin=${PYTHON_BIN:-$backend_dir/.venv/bin/python}
[[ -x $python_bin ]] || fail "Expected Python interpreter at $python_bin; run make backend-install"
export PYTHONUNBUFFERED=1
cd "$backend_dir"
exec "$python_bin" -m app.scripts.ingestion.backfill.metadata --machine "$selected_machine" "$@"
