#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "${SCRIPT_DIR}/../../../../" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${BACKEND_DIR}/.venv/bin/python}"

[[ -x "${PYTHON_BIN}" ]] || { echo "Missing backend Python environment" >&2; exit 1; }
: "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN must be set}"

export SIMBOARD_API_BASE_URL="${SIMBOARD_API_BASE_URL:-https://simboard-dev-api.e3sm.org}"
export MACHINE_NAME="${MACHINE_NAME:-perlmutter}"
export DRY_RUN="${DRY_RUN:-true}"

cd "${BACKEND_DIR}"
exec "${PYTHON_BIN}" -m app.scripts.ingestion.diagnostics_link_scanner "$@"
