"""Upload documented E3SM v3 cases from Chrysalis archive snapshots.

This targeted backfill reuses the remote HPC upload runner while filtering case
directories to simulations documented in the E3SM v3 data table. It packages
each selected case and sends it to ``/api/v1/ingestions/from-hpc-upload``. It
intentionally does not read or write whole-snapshot checkpoints because each
snapshot may also contain non-v3 cases needed by the general archive runner.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path, PurePosixPath

from app.scripts.ingestion.hpc_upload_archive_ingestor import (
    _run_ingestor as _run_upload_ingestor,
)
from app.scripts.ingestion.nersc_archive_ingestor import (
    IngestorConfig,
    IngestorRunReport,
    _build_config_from_env,
    _log_event,
)

V3_SIMULATION_TABLE_URL = (
    "https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/"
    "CoupledSystem/simulation_data/simulation_table.html"
)
V3_ARCHIVE_YEAR_START = "2024-01"
CHRYSALIS_ARCHIVE_ROOT = "/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF"
CHRYSALIS_MACHINE_NAME = "chrysalis"

# Values are copied from the source table's Simulation column. Some RFMIP
# entries include a grouping path; archive case directories use the leaf name.
V3_SIMULATIONS = (
    "v3.LR.piControl",
    "v3.LR.abrupt-4xCO2_0101_bcdt15m",
    "v3.LR.1pctCO2_0101_bcdt15m",
    "v3.LR.historical_0051",
    "v3.LR.historical_0101",
    "v3.LR.historical_0151",
    "v3.LR.historical_0201",
    "v3.LR.historical_0251",
    "v3.LR.hist-GHG_0101",
    "v3.LR.hist-GHG_0151",
    "v3.LR.hist-GHG_0201",
    "v3.LR.hist-aer_0101",
    "v3.LR.hist-aer_0151",
    "v3.LR.hist-aer_0201",
    "v3.LR.hist-xGHG-xaer_0101",
    "v3.LR.hist-xGHG-xaer_0151",
    "v3.LR.hist-xGHG-xaer_0201",
    "v3.LR.amip_0101",
    "v3.LR.amip_0151",
    "v3.LR.amip_0201",
    "v3.LR.piClim-control-iceini",
    "v3.LR.piClim-histall/v3.LR.piClim-histall_0101",
    "v3.LR.piClim-histall/v3.LR.piClim-histall_0151",
    "v3.LR.piClim-histall/v3.LR.piClim-histall_0201",
    "v3.LR.piClim-histGHG/v3.LR.piClim-histGHG_0101",
    "v3.LR.piClim-histGHG/v3.LR.piClim-histGHG_0151",
    "v3.LR.piClim-histGHG/v3.LR.piClim-histGHG_0201",
    "v3.LR.piClim-histaer/v3.LR.piClim-histaer_0101",
    "v3.LR.piClim-histaer/v3.LR.piClim-histaer_0151",
    "v3.LR.piClim-histaer/v3.LR.piClim-histaer_0201",
)


def _case_name(simulation: str) -> str:
    """Return archive case-directory name for one documented simulation."""
    return PurePosixPath(simulation).name


V3_CASE_NAMES_BY_SIMULATION = {
    simulation: _case_name(simulation) for simulation in V3_SIMULATIONS
}
V3_CASE_NAMES = frozenset(V3_CASE_NAMES_BY_SIMULATION.values())

if len(V3_CASE_NAMES) != len(V3_SIMULATIONS):
    raise RuntimeError("Documented v3 simulations must map to unique case names")


def _build_v3_config_from_env() -> IngestorConfig:
    """Build Chrysalis config with immutable v3 archive scan scope."""
    if not os.getenv("SIMBOARD_API_BASE_URL", "").strip():
        raise ValueError(
            "SIMBOARD_API_BASE_URL is required for remote Chrysalis uploads"
        )

    config = _build_config_from_env(
        scan_mode_override="archive",
        archive_year_start_override=V3_ARCHIVE_YEAR_START,
    )
    return replace(
        config,
        archive_root=Path(
            os.getenv("OLD_PERF_ARCHIVE_ROOT", CHRYSALIS_ARCHIVE_ROOT)
        ).resolve(),
        machine_name=CHRYSALIS_MACHINE_NAME,
    )


def _is_v3_case_path(case_path: Path) -> bool:
    """Return whether path exactly matches a documented v3 case name."""
    return case_path.name in V3_CASE_NAMES


def _matched_paths_by_case_name(
    report: IngestorRunReport,
) -> dict[str, list[str]]:
    """Group discovered archive paths by documented leaf case name."""
    matched_paths: defaultdict[str, list[str]] = defaultdict(list)
    for case_path in report.case_collection_data:
        case_name = Path(case_path).name
        if case_name in V3_CASE_NAMES:
            matched_paths[case_name].append(case_path)

    return {
        case_name: sorted(set(case_paths))
        for case_name, case_paths in matched_paths.items()
    }


def _log_v3_summary(report: IngestorRunReport, *, dry_run: bool) -> list[str]:
    """Log target reconciliation and return missing source simulations."""
    matched_paths = _matched_paths_by_case_name(report)
    missing_simulations: list[str] = []

    for simulation in V3_SIMULATIONS:
        case_name = V3_CASE_NAMES_BY_SIMULATION[simulation]
        case_paths = matched_paths.get(case_name, [])
        if case_paths:
            _log_event(
                "v3_case_match",
                {
                    "simulation": simulation,
                    "case_name": case_name,
                    "case_paths": case_paths,
                },
            )
        else:
            missing_simulations.append(simulation)
            _log_event(
                "v3_case_missing",
                {"simulation": simulation, "case_name": case_name},
            )

    stats = report.discovery_stats
    _log_event(
        "v3_ingestion_summary",
        {
            "mode": "dry-run" if dry_run else "ingest",
            "source_url": V3_SIMULATION_TABLE_URL,
            "expected_simulations": len(V3_SIMULATIONS),
            "matched_simulations": len(V3_SIMULATIONS) - len(missing_simulations),
            "missing_simulations": missing_simulations,
            "matching_case_directories": sum(
                len(case_paths) for case_paths in matched_paths.values()
            ),
            "execution_dirs_accepted": (
                0 if stats is None else stats["execution_dirs_accepted"]
            ),
            "rejected_existing_execution_ids": (
                0 if stats is None else stats["rejected_existing_execution_ids"]
            ),
            "rejected_incomplete_execution_ids": (
                0 if stats is None else stats["rejected_incomplete_execution_ids"]
            ),
            "rejected_invalid_execution_ids": (
                0 if stats is None else stats["rejected_invalid_execution_ids"]
            ),
            "transient_execution_ids": (
                0 if stats is None else stats["transient_execution_ids"]
            ),
            "deferred_execution_ids": (
                0 if stats is None else stats["deferred_execution_ids"]
            ),
            "submission_qualified_cases": report.submission_qualified_case_count,
            "selected_submission_cases": len(report.candidates),
            "ingestion_success_count": report.ingestion_success_count,
            "ingestion_failure_count": report.ingestion_failure_count,
        },
    )
    return missing_simulations


def main() -> int:
    """Run targeted v3 archive discovery and remote upload."""
    try:
        config = _build_v3_config_from_env()
    except ValueError as exc:
        _log_event("configuration_error", {"error": str(exc)})
        return 1

    started_at = time.monotonic()
    _log_event(
        "v3_run_started",
        {
            "mode": "dry-run" if config.dry_run else "ingest",
            "archive_root": str(config.archive_root),
            "archive_year_start": config.archive_year_start,
            "source_url": V3_SIMULATION_TABLE_URL,
        },
    )
    report = IngestorRunReport()
    exit_code = _run_upload_ingestor(
        config,
        case_path_filter=_is_v3_case_path,
        archive_checkpointing=False,
        run_report=report,
    )

    if report.scan_completed:
        missing_simulations = _log_v3_summary(report, dry_run=config.dry_run)
        transient_count = (
            0
            if report.discovery_stats is None
            else report.discovery_stats["transient_execution_ids"]
        )
        if missing_simulations or transient_count or not report.traversal_complete:
            exit_code = 1

    _log_event(
        "v3_run_finished",
        {
            "mode": "dry-run" if config.dry_run else "ingest",
            "exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - started_at, 3),
        },
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
