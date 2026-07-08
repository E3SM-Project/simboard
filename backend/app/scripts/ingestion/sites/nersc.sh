#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "${SCRIPT_DIR}/../../../../" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${BACKEND_DIR}/.venv/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Expected Python interpreter at ${PYTHON_BIN}" >&2
  echo "Run 'make install' from the repository root to create it." >&2
  exit 1
fi

: "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN must be set before running this script.}"

export SIMBOARD_API_BASE_URL="${SIMBOARD_API_BASE_URL:-https://simboard-dev-api.e3sm.org}"
export MACHINE_NAME="${MACHINE_NAME:-perlmutter}"
export SCAN_MODE="${SCAN_MODE:-archive}"
export DRY_RUN="${DRY_RUN:-true}"
export PERF_ARCHIVE_ROOT="${PERF_ARCHIVE_ROOT:-/global/cfs/projectdirs/e3sm/performance_archive}"
export OLD_PERF_ARCHIVE_ROOT="${OLD_PERF_ARCHIVE_ROOT:-/global/cfs/projectdirs/e3sm/OLD_PERF}"

if [[ "${SCAN_MODE}" != "staging" && "${SCAN_MODE}" != "archive" ]]; then
  echo "SCAN_MODE must be either 'staging' or 'archive'." >&2
  exit 1
fi

cd "${BACKEND_DIR}"
exec "${PYTHON_BIN}" -m app.scripts.ingestion.nersc_archive_ingestor "$@"
