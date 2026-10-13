#!/usr/bin/env bash

# Opt-in ACL deployments inherit named-user entries from directory defaults.
# Group mode bits are the ACL mask, not the owning group's permissions. Keep
# the mask writable when mkdir would otherwise reduce it to read-only.
operations_acl_enabled() {
  [[ -f "$1/.simboard-acl-enabled" && ! -L "$1/.simboard-acl-enabled" ]]
}

operations_install() {
  local source=$1 destination=$2 directory defaults
  directory="$(dirname -- "$destination")"
  if operations_acl_enabled "$directory"; then
    # GNU install strips ACLs. Create by redirection to inherit defaults, then
    # preserve named-user entries while setting their effective mask to rw.
    defaults="$(getfacl -cp -- "$directory")" || return 1
    if [[ "$defaults" != *'default:group::---'* || "$defaults" != *'default:other::---'* ]]; then
      echo "Managed directory is missing restrictive default ACLs: $directory" >&2
      return 1
    fi
    (umask 077; set -o noclobber; cat -- "$source" > "$destination") || return 1
    chmod 660 "$destination"
  else
    install -m 640 -- "$source" "$destination"
  fi
}

operations_directory_mode() {
  if operations_acl_enabled "$1"; then
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
