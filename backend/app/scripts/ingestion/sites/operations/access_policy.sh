#!/usr/bin/env bash

# Opt-in ACL deployments inherit named-user entries from directory defaults.
# Group mode bits are the ACL mask, not the owning group's permissions. Keep
# the mask writable when mkdir would otherwise reduce it to read-only.
operations_acl_enabled() {
  [[ -f "$1/.simboard-acl-enabled" && ! -L "$1/.simboard-acl-enabled" ]]
}

operations_default_acl() {
  getfacl -cpn -- "$1" | while IFS= read -r entry; do
    case "$entry" in default:*) printf '%s\n' "$entry" ;; esac
  done | LC_ALL=C sort
}

operations_validate_defaults() {
  local directory=$1 policy_directory=${2:-$1} expected actual
  expected="$(cat -- "$policy_directory/.simboard-acl-enabled")" || return 1
  actual="$(operations_default_acl "$directory")" || return 1
  if [[ -z "$expected" || "$actual" != "$expected" ]]; then
    echo "Managed directory is missing restrictive default ACLs or configured operator defaults have drifted: $directory. Re-run operations-configure-access." >&2
    return 1
  fi
}

operations_install() {
  local source=$1 destination=$2 directory
  directory="$(dirname -- "$destination")"
  if operations_acl_enabled "$directory"; then
    # GNU install strips ACLs. Create by redirection to inherit defaults, then
    # preserve named-user entries while setting their effective mask to rw.
    operations_validate_defaults "$directory" || return 1
    (umask 077; set -o noclobber; cat -- "$source" > "$destination") || return 1
    chmod 660 "$destination"
  else
    install -m 640 -- "$source" "$destination"
  fi
}

operations_directory_mode() {
  if operations_acl_enabled "$1"; then
    operations_validate_defaults "$1" || return 1
    printf '770\n'
  else
    printf '750\n'
  fi
}

# Also used by the Makefile to install a copied crontab.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  if (( $# != 2 )); then
    echo "Usage: $0 <source> <destination>" >&2
    exit 1
  fi
  operations_install "$1" "$2"
fi
