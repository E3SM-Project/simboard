#!/usr/bin/env bash
set -euo pipefail

# Refresh an existing clean deployment checkout. Bootstrap directories and a
# missing checkout with operations-provision instead.
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set}"
repository_ref="${SIMBOARD_REPOSITORY_REF:-main}"
operations_dir="${SIMBOARD_ROOT}/operations"
checkout_dir="${SIMBOARD_ROOT}/repository/simboard"
deployed_helper="${checkout_dir}/backend/app/scripts/ingestion/sites/operations/refresh_repository.sh"

if ! command -v git >/dev/null || ! command -v make >/dev/null || ! command -v flock >/dev/null; then
  echo "git, make, and flock must be available to refresh the SimBoard checkout" >&2
  exit 1
fi

if [[ ! -d "${operations_dir}" ]]; then
  echo "Operations directory does not exist; run operations-provision first: ${operations_dir}" >&2
  exit 1
fi

if [[ ! -d "${checkout_dir}/.git" ]]; then
  echo "SimBoard checkout does not exist; run operations-provision first: ${checkout_dir}" >&2
  exit 1
fi

# Cron invokes the helper from the checkout it refreshes. Re-execute a private
# copy so `git checkout` cannot replace the script Bash is still reading.
if [[ "${BASH_SOURCE[0]}" == "${deployed_helper}" && -z "${SIMBOARD_REFRESH_TEMP_SCRIPT:-}" ]]; then
  refresh_temp_script="$(mktemp "${operations_dir}/.refresh_repository.XXXXXX")"
  cp "${BASH_SOURCE[0]}" "${refresh_temp_script}"
  chmod 700 "${refresh_temp_script}"
  SIMBOARD_REFRESH_TEMP_SCRIPT="${refresh_temp_script}" exec bash "${refresh_temp_script}"
fi

if [[ -n "${SIMBOARD_REFRESH_TEMP_SCRIPT:-}" ]]; then
  trap 'rm -f "${SIMBOARD_REFRESH_TEMP_SCRIPT}"' EXIT
fi

refresh_lock_file="${operations_dir}/SBCS-provision.lock"
exec 201>"${refresh_lock_file}"
if ! flock -n 201; then
  echo "SimBoard repository refresh already running: ${checkout_dir}"
  exit 0
fi

if [[ -n "$(git -C "${checkout_dir}" status --porcelain)" ]]; then
  echo "SimBoard checkout has uncommitted changes: ${checkout_dir}" >&2
  exit 1
fi

current_revision="$(git -C "${checkout_dir}" rev-parse HEAD)"
git -C "${checkout_dir}" fetch --depth 1 origin "${repository_ref}"
updated_revision="$(git -C "${checkout_dir}" rev-parse FETCH_HEAD)"

if [[ "${current_revision}" == "${updated_revision}" ]]; then
  echo "SimBoard checkout is already current: ${checkout_dir} (${current_revision})"
  exit 0
fi

git -C "${checkout_dir}" checkout --detach --force FETCH_HEAD
make -C "${checkout_dir}" backend-install
echo "Refreshed SimBoard checkout: ${checkout_dir} (${current_revision} -> ${updated_revision})"
