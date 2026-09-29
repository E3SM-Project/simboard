#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INGESTION_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="$(cd -- "${INGESTION_DIR}/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${BACKEND_DIR}/.venv/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >&2
  echo "Run 'make install' from the repository root to create it." >&2
  exit 1
fi

: "${ENV_FILE:?ENV_FILE must identify a readable environment file.}"
if [[ ! -f "${ENV_FILE}" || ! -r "${ENV_FILE}" ]]; then
  echo "ENV_FILE must identify a readable file: ${ENV_FILE}" >&2
  exit 1
fi

requested_dry_run="${DRY_RUN:-}"
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

: "${SIMBOARD_API_BASE_URL:?SIMBOARD_API_BASE_URL must be set in ENV_FILE.}"
export DRY_RUN="${requested_dry_run:-${DRY_RUN:-true}}"

SIZE_ARGS=()
if [[ "${INCLUDE_SIZES:-false}" == "true" ]]; then
  SIZE_ARGS+=(--include-sizes)
fi

TRUST_ARGS=()
if [[ "${TRUST_EXISTING:-false}" == "true" ]]; then
  TRUST_ARGS+=(--trust-existing)
fi

DRY_RUN_NORMALIZED="${DRY_RUN,,}"
if [[ "${DRY_RUN_NORMALIZED}" != "true" && "${DRY_RUN}" != "1" && "${DRY_RUN_NORMALIZED}" != "yes" ]]; then
  : "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN must be set in ENV_FILE when DRY_RUN is false.}"
fi

cd "${BACKEND_DIR}"
exec "${PYTHON_BIN}" -m app.scripts.ingestion.v3_data.diagnostics_backfill \
  --machine chrysalis "${SIZE_ARGS[@]}" "${TRUST_ARGS[@]}" "$@"
