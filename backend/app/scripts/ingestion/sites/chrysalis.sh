#!/usr/bin/env bash
set -euo pipefail

# Thin SimBoard entrypoint for the existing Chrysalis Jenkins workflow.
# Keep site-specific setup here; keep ingestion logic in hpc_archive_ingestor.py.

: "${SIMBOARD_API_BASE_URL:?SIMBOARD_API_BASE_URL is required}"
: "${SIMBOARD_API_TOKEN:?SIMBOARD_API_TOKEN is required}"

export MACHINE_NAME="${MACHINE_NAME:-chrysalis}"
export PERF_ARCHIVE_ROOT="${PERF_ARCHIVE_ROOT:-/lcrc/group/e3sm/PERF_Chrysalis/performance_archive}"
export STATE_PATH="${STATE_PATH:-${PERF_ARCHIVE_ROOT}/../simboard-ingestion-state.json}"
export DRY_RUN="${DRY_RUN:-true}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_root="$(cd "${script_dir}/../../../.." && pwd)"
python_bin="${PYTHON_BIN:-python}"

cd "${backend_root}"
exec "${python_bin}" -m app.scripts.ingestion.hpc_archive_ingestor
