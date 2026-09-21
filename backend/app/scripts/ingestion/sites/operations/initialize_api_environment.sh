#!/usr/bin/env bash
set -euo pipefail

if (( $# != 3 )); then
  echo "Usage: $0 <dev|prod> <template> <destination>" >&2
  exit 1
fi

environment=$1
template=$2
destination=$3

case "${environment}" in
  dev) environment_name="Development" ;;
  prod) environment_name="Production" ;;
  *)
    echo "Environment must be dev or prod: ${environment}" >&2
    exit 1
    ;;
esac

if [[ ! -r "${template}" ]]; then
  echo "Environment template not readable: ${template}" >&2
  exit 1
fi

if [[ -e "${destination}" ]]; then
  echo "Destination already exists: ${destination}" >&2
  exit 1
fi

# Templates are committed shell files that provide the environment-specific
# public API URL. Source the selected template only to obtain that default.
source "${template}"
default_api_base_url="${SIMBOARD_API_BASE_URL:-}"

read -r -p "${environment} SIMBOARD_API_BASE_URL [${default_api_base_url}]: " api_base_url
api_base_url="${api_base_url:-${default_api_base_url}}"
read -r -s -p "${environment} SIMBOARD_API_TOKEN: " api_token
printf '\n'

if [[ -z "${api_base_url}" ]]; then
  echo "SIMBOARD_API_BASE_URL must be set" >&2
  exit 1
fi

if [[ -z "${api_token}" ]]; then
  echo "SIMBOARD_API_TOKEN must be set" >&2
  exit 1
fi

install -m 640 /dev/null "${destination}"
{
  printf '#!/usr/bin/env bash\n'
  printf '# %s SimBoard API configuration. Keep this file outside the repository.\n' \
    "${environment_name}"
  printf 'export SIMBOARD_API_BASE_URL=%q\n' "${api_base_url}"
  printf 'export SIMBOARD_API_TOKEN=%q\n' "${api_token}"
} >> "${destination}"
