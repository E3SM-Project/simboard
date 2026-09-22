#!/usr/bin/env bash

set -euo pipefail

if (( $# != 4 )); then
  echo "Usage: $0 <api-template> <v3-template> <destination> <environment>" >&2
  exit 1
fi

api_template=$1
v3_template=$2
destination=$3
environment=$4

for template in "${api_template}" "${v3_template}"; do
  if [[ ! -r "${template}" ]]; then
    echo "Environment template not readable: ${template}" >&2
    exit 1
  fi
done

if [[ -e "${destination}" ]]; then
  echo "Destination already exists: ${destination}" >&2
  exit 1
fi

# These committed templates contain defaults only and are safe to source.
source "${api_template}"
default_api_base_url="${SIMBOARD_API_BASE_URL:-}"
source "${v3_template}"
default_diagnostics_source_root="${V3_DIAGNOSTICS_SOURCE_ROOT:-}"

read -r -p "${environment} SIMBOARD_API_BASE_URL [${default_api_base_url}]: " api_base_url
api_base_url="${api_base_url:-${default_api_base_url}}"
read -r -s -p "${environment} SIMBOARD_API_TOKEN: " api_token
printf '\n'
read -r -p "${environment} V3_DIAGNOSTICS_SOURCE_ROOT [${default_diagnostics_source_root}]: " diagnostics_source_root
diagnostics_source_root="${diagnostics_source_root:-${default_diagnostics_source_root}}"

if [[ -z "${api_base_url}" || -z "${api_token}" || -z "${diagnostics_source_root}" ]]; then
  echo "SIMBOARD_API_BASE_URL, SIMBOARD_API_TOKEN, and V3_DIAGNOSTICS_SOURCE_ROOT must be set" >&2
  exit 1
fi

install -m 640 /dev/null "${destination}"
{
  printf '# %s E3SM v3 Chrysalis backfill configuration. Keep outside the repository.\n' "${environment}"
  printf 'SIMBOARD_API_BASE_URL=%q\n' "${api_base_url}"
  printf 'SIMBOARD_API_TOKEN=%q\n' "${api_token}"
  printf 'V3_DIAGNOSTICS_SOURCE_ROOT=%q\n' "${diagnostics_source_root}"
  printf '\n# Optional: override the default historical archive mount.\n'
  printf '# OLD_PERF_ARCHIVE_ROOT=/path/to/OLD_PERF\n'
} >> "${destination}"
