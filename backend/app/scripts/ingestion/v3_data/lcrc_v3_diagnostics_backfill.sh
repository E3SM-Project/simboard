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

: "${LCRC_V3_ENV_FILE:?LCRC_V3_ENV_FILE must identify a readable environment file.}"
if [[ ! -f "${LCRC_V3_ENV_FILE}" || ! -r "${LCRC_V3_ENV_FILE}" ]]; then
  echo "LCRC_V3_ENV_FILE must identify a readable file: ${LCRC_V3_ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${LCRC_V3_ENV_FILE}"
set +a

: "${SIMBOARD_API_BASE_URL:?SIMBOARD_API_BASE_URL must be set in LCRC_V3_ENV_FILE.}"
export DRY_RUN="${LCRC_V3_DRY_RUN:-${DRY_RUN:-true}}"

SIZE_ARGS=()
if [[ "${V3_DIAGNOSTICS_INCLUDE_SIZES:-false}" == "true" ]]; then
  SIZE_ARGS+=(--include-sizes)
fi

DRY_RUN_NORMALIZED="${DRY_RUN,,}"
if [[ "${DRY_RUN_NORMALIZED}" != "true" && "${DRY_RUN}" != "1" && "${DRY_RUN_NORMALIZED}" != "yes" ]]; then
  : "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN must be set in LCRC_V3_ENV_FILE when DRY_RUN is false.}"
fi

cd "${BACKEND_DIR}"
exec "${PYTHON_BIN}" -m app.scripts.ingestion.v3_data.diagnostics_backfill \
  --machine chrysalis "${SIZE_ARGS[@]}" "$@"
