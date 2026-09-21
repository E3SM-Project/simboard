#!/usr/bin/env bash
set -euo pipefail

# Provision the deployment-local workspace and SimBoard checkout used by
# scheduled site ingestion. Credentials and installed crontabs are created
# separately and never stored in the repository.
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set}"
repository_url="${SIMBOARD_REPOSITORY_URL:-https://github.com/E3SM-Project/simboard.git}"
repository_ref="${SIMBOARD_REPOSITORY_REF:-main}"

if [[ ! -d "${SIMBOARD_ROOT}" ]]; then
  echo "SIMBOARD_ROOT is not an existing directory: ${SIMBOARD_ROOT}" >&2
  exit 1
fi

if ! command -v git >/dev/null; then
  echo "git must be available to provision the SimBoard checkout" >&2
  exit 1
fi

operations_dir="${SIMBOARD_ROOT}/operations"

if [[ ( -e "${operations_dir}" || -L "${operations_dir}" ) && ! -d "${operations_dir}" ]]; then
  echo "Operations path exists but is not a directory: ${operations_dir}" >&2
  exit 1
fi

if [[ -d "${operations_dir}" ]]; then
  echo "Verified existing operations directory: ${operations_dir}"
else
  mkdir -m 750 "${operations_dir}"
  echo "Created operations directory: ${operations_dir}"
fi

repository_dir="${SIMBOARD_ROOT}/repository"
checkout_dir="${repository_dir}/simboard"

if [[ -e "${repository_dir}" && ! -d "${repository_dir}" ]]; then
  echo "Repository path exists but is not a directory: ${repository_dir}" >&2
  exit 1
fi

mkdir -p "${repository_dir}"

if [[ -e "${checkout_dir}" && ! -d "${checkout_dir}/.git" ]]; then
  echo "SimBoard checkout is not a Git repository: ${checkout_dir}" >&2
  exit 1
fi

if [[ -d "${checkout_dir}/.git" ]]; then
  if [[ -n "$(git -C "${checkout_dir}" status --porcelain)" ]]; then
    echo "SimBoard checkout has uncommitted changes: ${checkout_dir}" >&2
    exit 1
  fi
  git -C "${checkout_dir}" fetch --depth 1 origin "${repository_ref}"
  git -C "${checkout_dir}" checkout --detach --force FETCH_HEAD
  echo "Updated SimBoard checkout: ${checkout_dir}"
else
  git clone --branch "${repository_ref}" --single-branch --depth 1 \
    "${repository_url}" "${checkout_dir}"
  echo "Cloned SimBoard checkout: ${checkout_dir}"
fi
