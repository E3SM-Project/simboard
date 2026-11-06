#!/usr/bin/env bash
set -euo pipefail

if (( $# != 4 )); then
  echo "Usage: $0 <template> <destination> <site> <diagnostics-enabled>" >&2
  exit 1
fi

template=$1
destination=$2
site=$3
diagnostics_enabled=$4
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

[[ -r $template ]] || { echo "Scheduler template not readable: $template" >&2; exit 1; }
[[ $site =~ ^[a-z0-9_-]+$ ]] || { echo "Invalid site name: $site" >&2; exit 1; }

# Render to a private temporary file, then use the same install helper as all
# other protected operations artifacts so restrictive modes/ACLs are preserved.
temporary="$(mktemp "${TMPDIR:-/tmp}/simboard-scheduler.XXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
if [[ $diagnostics_enabled == true ]]; then
  sed \
    -e "s/__SIMBOARD_SITE__/${site}/g" \
    -e '/^# __SIMBOARD_DIAGNOSTICS_BEGIN__$/d' \
    -e '/^# __SIMBOARD_DIAGNOSTICS_END__$/d' \
    "$template" > "$temporary"
else
  # Sites without a reviewed diagnostics archive get no diagnostics jobs at all,
  # rather than scheduled jobs that fail every run.
  sed \
    -e "s/__SIMBOARD_SITE__/${site}/g" \
    -e '/^# __SIMBOARD_DIAGNOSTICS_BEGIN__$/,/^# __SIMBOARD_DIAGNOSTICS_END__$/d' \
    "$template" > "$temporary"
fi
# shellcheck source=access_policy.sh
source "${script_dir}/access_policy.sh"
operations_install "$temporary" "$destination"
