#!/usr/bin/env bash
set -euo pipefail
umask 027

# Provision the deployment-local workspace and SimBoard checkout used by
# scheduled site ingestion. Credentials and installed crontabs are created
# separately and never stored in the repository.
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set}"
repository_url="${SIMBOARD_REPOSITORY_URL:-https://github.com/E3SM-Project/simboard.git}"
repository_ref="${SIMBOARD_REPOSITORY_REF:-main}"

if [[ ( -e "${SIMBOARD_ROOT}" || -L "${SIMBOARD_ROOT}" ) && ! -d "${SIMBOARD_ROOT}" ]]; then
  echo "SIMBOARD_ROOT exists but is not a directory: ${SIMBOARD_ROOT}" >&2
  exit 1
fi

if [[ -d "${SIMBOARD_ROOT}" ]]; then
  echo "Verified existing SimBoard deployment root: ${SIMBOARD_ROOT}"
else
  mkdir -p -m 750 "${SIMBOARD_ROOT}"
  echo "Created SimBoard deployment root: ${SIMBOARD_ROOT}"
fi

if ! command -v git >/dev/null || ! command -v make >/dev/null; then
  echo "git and make must be available to provision SimBoard operations" >&2
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
  mkdir -p -m 750 "${operations_dir}"
  echo "Created operations directory: ${operations_dir}"
fi

# Runtime logs and operator-reviewed validation artifacts are deliberately kept
# separate. Do not create summarized_logs until a summary-producing workflow is
# introduced.
for directory_name in raw_logs quality_assurance; do
  directory_path="${operations_dir}/${directory_name}"
  if [[ ( -e "${directory_path}" || -L "${directory_path}" ) && ! -d "${directory_path}" ]]; then
    echo "Operations ${directory_name} path exists but is not a directory: ${directory_path}" >&2
    exit 1
  fi
  if [[ -d "${directory_path}" ]]; then
    echo "Verified existing operations ${directory_name} directory: ${directory_path}"
  else
    mkdir -p -m 750 "${directory_path}"
    echo "Created operations ${directory_name} directory: ${directory_path}"
  fi
done

if command -v getent >/dev/null 2>&1 && getent group simboard >/dev/null 2>&1; then
  for directory_path in "${operations_dir}" "${operations_dir}/raw_logs" "${operations_dir}/quality_assurance"; do
    if ! chgrp simboard "${directory_path}"; then
      echo "Unable to set simboard group ownership: ${directory_path}" >&2
      exit 1
    fi
    chmod 2750 "${directory_path}"
  done
  echo "Configured simboard group access for operations artifacts"
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

make -C "${checkout_dir}" backend-install
echo "Installed SimBoard backend runtime: ${checkout_dir}/backend/.venv"
