#!/usr/bin/env bash
set -euo pipefail

if (( $# != 4 )); then
  echo "Usage: $0 <dev-template> <prod-template> <dev-destination> <prod-destination>" >&2
  exit 1
fi

dev_template=$1
prod_template=$2
dev_destination=$3
prod_destination=$4

for template in "${dev_template}" "${prod_template}"; do
  if [[ ! -r "${template}" ]]; then
    echo "Environment template not readable: ${template}" >&2
    exit 1
  fi
done

for destination in "${dev_destination}" "${prod_destination}"; do
  if [[ -e "${destination}" ]]; then
    echo "Destination already exists: ${destination}" >&2
    exit 1
  fi
done

prompt_environment() {
  local environment=$1
  local template=$2
  local api_base_url api_token

  # Templates are committed shell files that provide the environment-specific
  # public API URL. Source the selected template only to obtain that default.
  source "${template}"
  local default_api_base_url="${SIMBOARD_API_BASE_URL:-}"

  read -r -p "${environment} SIMBOARD_API_BASE_URL [${default_api_base_url}]: " api_base_url
  api_base_url="${api_base_url:-${default_api_base_url}}"
  read -r -s -p "${environment} SIMBOARD_API_TOKEN: " api_token
  printf '\n'

  if [[ -z "${api_base_url}" || -z "${api_token}" ]]; then
    echo "${environment} SIMBOARD_API_BASE_URL and SIMBOARD_API_TOKEN must be set" >&2
    exit 1
  fi

  PROMPTED_API_BASE_URL="${api_base_url}"
  PROMPTED_API_TOKEN="${api_token}"
}

prompt_environment dev "${dev_template}"
dev_api_base_url="${PROMPTED_API_BASE_URL}"
dev_api_token="${PROMPTED_API_TOKEN}"
prompt_environment prod "${prod_template}"
prod_api_base_url="${PROMPTED_API_BASE_URL}"
prod_api_token="${PROMPTED_API_TOKEN}"

write_environment() {
  local environment_name=$1
  local destination=$2
  local api_base_url=$3
  local api_token=$4

  install -m 640 /dev/null "${destination}"
  {
  printf '#!/usr/bin/env bash\n'
  printf '# %s SimBoard API configuration. Keep this file outside the repository.\n' \
    "${environment_name}"
  printf 'export SIMBOARD_API_BASE_URL=%q\n' "${api_base_url}"
  printf 'export SIMBOARD_API_TOKEN=%q\n' "${api_token}"
  } >> "${destination}"
}

write_environment Development "${dev_destination}" "${dev_api_base_url}" "${dev_api_token}"
write_environment Production "${prod_destination}" "${prod_api_base_url}" "${prod_api_token}"
