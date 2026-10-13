#!/usr/bin/env bash
set -euo pipefail
umask 077

fail() {
  echo "$*" >&2
  exit 1
}

has_execute_bit() {
  local mode
  mode="$(stat -c %a -- "$1")" || return 1
  (( (8#$mode & 0111) != 0 ))
}

if (( $# != 3 )); then
  fail "Usage: $0 <site> <space-separated-operators> <false|true>"
fi
site=$1
operator_input=$2
apply=$3
: "${SIMBOARD_ROOT:?SIMBOARD_ROOT must be set}"
[[ "$site" =~ ^[a-z0-9_-]+$ ]] || fail "Invalid site name"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -r "$script_dir/../configs/$site.config" ]] || fail "Site configuration not readable: $site"
[[ "$apply" == false || "$apply" == true ]] || fail "apply must be false or true"

for tool in getfacl setfacl getent realpath find stat mktemp sort; do
  command -v "$tool" > /dev/null || fail "$tool is required for ACL configuration"
done
[[ -d "$SIMBOARD_ROOT/operations" ]] || fail "Operations directory does not exist; provision it first"
root="$(realpath -e -- "$SIMBOARD_ROOT")"
[[ "$root" != / ]] || fail "Refusing to configure the filesystem root"
[[ "$(realpath -s -- "$SIMBOARD_ROOT")" == "$root" ]] || fail "Deployment path must not contain symlinks"
operations_dir="$root/operations"
[[ ! -L "$operations_dir" ]] || fail "Operations directory must not be a symlink"

operators=()
read -r -a operators <<< "$operator_input"
(( ${#operators[@]} > 0 )) || fail "At least one operator is required"
directory_acl='u::rwx,g::---,m::rwx,o::---'
default_acl='d:u::rwx,d:g::---,d:m::rwx,d:o::---'
file_acl='u::rw-,g::---,m::rw-,o::---'
executable_acl='u::rwx,g::---,m::rwx,o::---'
root_acl=''
for operator in "${operators[@]}"; do
  [[ "$operator" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || fail "Invalid operator username: $operator"
  getent passwd "$operator" > /dev/null || fail "Unknown operator: $operator"
  directory_acl+=",u:$operator:rwx"
  default_acl+=",d:u:$operator:rwx"
  file_acl+=",u:$operator:rw-"
  executable_acl+=",u:$operator:rwx"
  root_acl+="${root_acl:+,}u:$operator:--x"
done

# Preflight every entry before changing any permissions. Do not follow links,
# cross filesystem boundaries, or change hard-linked files outside this tree.
paths=()
exec 3< <(find "$operations_dir" -xdev -print0)
find_pid=$!
while IFS= read -r -d '' path; do
  paths+=("$path")
done <&3
exec 3<&-
wait "$find_pid" || fail "Cannot enumerate operations entries"
operations_device="$(stat -c %d -- "$operations_dir")"
for path in "$root" "${paths[@]}"; do
  [[ ! -L "$path" ]] || fail "Refusing symlink: $path"
  [[ -d "$path" || -f "$path" ]] || fail "Unsupported entry: $path"
  [[ "$(stat -c %u -- "$path")" == "$EUID" ]] || fail "Current user must own: $path. ACL write access does not permit changing another owner's ACL; coordinate with the file owner or site admin."
  if [[ -f "$path" && "$(stat -c %h -- "$path")" != 1 ]]; then
    fail "Refusing hard-linked file: $path"
  fi
  [[ "$(stat -c %d -- "$path")" == "$operations_device" || "$path" == "$root" ]] || fail "Refusing nested filesystem: $path"
  getfacl -cp -- "$path" > /dev/null || fail "Cannot inspect ACL: $path"
done

# Preserve the root's existing permissions; do not expand previously masked
# group entries when adding traversal. A root mask without x needs owner review.
root_permissions="$(getfacl -cp -- "$root")"
if [[ "$root_permissions" == *'mask::'* ]]; then
  root_mask="$(printf '%s\n' "$root_permissions" | while IFS= read -r line; do
    case "$line" in mask::*) printf '%s\n' "${line#mask::}" ;; esac
  done)"
  [[ "$root_mask" == *x* ]] || fail "Deployment root ACL mask must permit traversal before configuration"
fi

printf 'Site: %s\nOperations scope: %s\nOperators: %s\n' "$site" "$operations_dir" "$operator_input"
printf 'Replace operations ACLs: directories rwx; files rw; executable files rwx.\n'
printf 'Set directory defaults; remove access for unlisted users and groups.\n'
printf 'Grant named operators traversal on the deployment root only.\n'
printf 'WARNING: Check parent traversal and parent write permissions separately.\n'
printf 'WARNING: Stop scheduled jobs first; all operators can read credentials and modify operations files.\n'
if [[ "$apply" == false ]]; then
  printf 'Preview only. Re-run with apply=true to change permissions.\n'
  exit 0
fi

# Probe actual filesystem ACL support before changing deployment permissions.
probe="$(mktemp "$operations_dir/.acl-probe.XXXXXX")"
trap 'rm -f -- "$probe"' EXIT
setfacl -m "$file_acl" -- "$probe" || fail "Filesystem does not support the requested ACLs"
rm -f -- "$probe"
trap - EXIT

backup="$(mktemp "$root/.simboard-acl-backup.XXXXXX")"
chmod 600 "$backup"
getfacl -p -- "$root" > "$backup"
for path in "${paths[@]}"; do
  getfacl -p -- "$path" >> "$backup"
done
printf 'ACL backup: %s\nRestore with: setfacl --restore=%q\n' "$backup" "$backup"
if [[ ! -e "$operations_dir/.simboard-acl-enabled" ]]; then
  printf 'After restoring this backup, remove %s/.simboard-acl-enabled to disable ACL-aware creation.\n' "$operations_dir"
fi
trap 'echo "ACL configuration failed; changes may be partial. Restore from the printed backup." >&2' ERR

# Without an existing mask, setfacl derives it from the root's existing group
# permissions plus the added traversal entries. With a mask, preserve it.
if [[ "$root_permissions" == *'mask::'* ]]; then
  setfacl -n -m "$root_acl" -- "$root"
else
  setfacl -m "$root_acl" -- "$root"
fi
for path in "${paths[@]}"; do
  if [[ -d "$path" ]]; then
    setfacl -k -- "$path"
    setfacl --set "$directory_acl,$default_acl" -- "$path"
  elif has_execute_bit "$path"; then
    setfacl --set "$executable_acl" -- "$path"
  else
    setfacl --set "$file_acl" -- "$path"
  fi
done

# The marker opts existing creation helpers into preserving the inherited mask.
marker="$operations_dir/.simboard-acl-enabled"
touch "$marker"
setfacl --set "$file_acl" -- "$marker"

# Verify exact ACLs, not just command exit status. getfacl includes no contents.
verify_acl() {
  local path=$1 specification=$2 entry actual expected
  local entries=()
  IFS=, read -r -a entries <<< "$specification"
  expected="$(for entry in "${entries[@]}"; do
    entry="${entry/#d:u:/default:user:}"
    entry="${entry/#d:g:/default:group:}"
    entry="${entry/#d:m:/default:mask:}"
    entry="${entry/#d:o:/default:other:}"
    entry="${entry/#u:/user:}"
    entry="${entry/#g:/group:}"
    entry="${entry/#m:/mask:}"
    entry="${entry/#o:/other:}"
    printf '%s\n' "$entry"
  done | LC_ALL=C sort -u)"
  actual="$(getfacl -cp -- "$path" | while IFS= read -r entry; do
    [[ -z "$entry" ]] || printf '%s\n' "$entry"
  done | LC_ALL=C sort -u)"
  [[ "$actual" == "$expected" ]] || fail "ACL verification failed: $path; restore from $backup"
}
for path in "${paths[@]}" "$marker"; do
  if [[ -d "$path" ]]; then
    expected="$directory_acl,$default_acl"
  elif has_execute_bit "$path"; then
    expected="$executable_acl"
  else
    expected="$file_acl"
  fi
  verify_acl "$path" "$expected"
done
printf 'Configured operations ACLs. Verify access from each operator account.\n'
