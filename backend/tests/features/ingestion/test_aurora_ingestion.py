"""Offline end-to-end proof that Aurora metadata can enter SimBoard discovery.

The tree mirrors what PACE's Aurora collector leaves on disk: ``OLD_PERF``
nested inside the staging root, processed batches still at the top level, and
``pace-exps-*`` upload work trees. Runs go through SimBoard's real parser and
remote-site ingestor with every network and write phase disabled.
"""

from __future__ import annotations

from pathlib import Path

from app.features.ingestion.parsers.parser import main_parser
from app.scripts.ingestion.archive_ingestor_core import (
    IngestorConfig,
    IngestorRunReport,
)
from app.scripts.ingestion.hpc_upload_archive_ingestor import _run_ingestor
from tests.fixtures.aurora_case import (
    ARCHIVE_MONTH,
    ARCHIVED_EXECUTION_ID,
    CASE_NAME,
    EXECUTION_ID,
    HPC_USERNAME,
    stage_aurora_case,
    stage_aurora_performance_root,
)


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    """Return relative paths and bytes so a dry run can prove it changed nothing."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def _must_not_run(*_args, **_kwargs):
    raise AssertionError("offline dry-run reached a network, packaging, or write phase")


def _offline_config(root: Path, scan_mode: str, **extra) -> IngestorConfig:
    return IngestorConfig(
        api_base_url="",
        api_token="",
        archive_root=root,
        machine_name="aurora",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=5,
        scan_mode=scan_mode,  # type: ignore[arg-type]
        dry_run_use_remote_state=False,
        **extra,
    )


def _run_offline(config: IngestorConfig, report: IngestorRunReport) -> int:
    return _run_ingestor(
        config,
        post_request_fn=_must_not_run,
        discovery_post_request_fn=_must_not_run,
        checkpoint_post_request_fn=_must_not_run,
        source_directory_post_request_fn=_must_not_run,
        run_report=report,
    )


def test_real_parser_recognizes_aurora_identity(tmp_path: Path) -> None:
    case = stage_aurora_case(tmp_path / "performance_archive" / HPC_USERNAME)

    parsed, skipped = main_parser(case, tmp_path / "parsed", strict_validation=True)

    assert skipped == 0
    assert len(parsed) == 1
    execution = parsed[0]
    assert execution.machine == "aurora"
    assert execution.execution_id == EXECUTION_ID
    assert execution.case_name == CASE_NAME
    assert execution.hpc_username == HPC_USERNAME
    assert execution.compiler == "oneapi-ifx"


def test_aurora_staging_scans_only_live_output(tmp_path: Path) -> None:
    staging_root = tmp_path / "performance_archive"
    stage_aurora_performance_root(staging_root)
    before = _tree_snapshot(staging_root)
    report = IngestorRunReport()

    result = _run_offline(_offline_config(staging_root, "staging"), report)

    assert result == 0
    assert report.scan_completed is True
    assert report.submission_qualified_case_count == 1
    assert len(report.candidates) == 1
    candidate = report.candidates[0]
    assert candidate.case_path == str(staging_root / HPC_USERNAME / CASE_NAME)
    assert candidate.execution_ids == [EXECUTION_ID]
    assert report.discovery_stats is not None
    # OLD_PERF, the leftover batch, and the upload work tree are never entered.
    assert report.discovery_stats["execution_dirs_scanned"] == 1
    assert report.discovery_stats["execution_dirs_accepted"] == 1
    assert _tree_snapshot(staging_root) == before


def test_aurora_archive_reads_nested_old_perf_completed_bucket(
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "performance_archive"
    archive_root = stage_aurora_performance_root(staging_root)
    before = _tree_snapshot(staging_root)
    report = IngestorRunReport()

    result = _run_offline(
        _offline_config(
            archive_root,
            "archive",
            archive_year_start="2025-01",
        ),
        report,
    )

    assert result == 0
    assert report.submission_qualified_case_count == 1
    assert report.candidates[0].execution_ids == [ARCHIVED_EXECUTION_ID]
    assert report.discovery_stats is not None
    # The FAILED bucket is pruned; only the COMPLETED execution is scanned.
    assert report.discovery_stats["execution_dirs_scanned"] == 1
    assert report.discovery_stats["execution_dirs_accepted"] == 1
    assert ARCHIVE_MONTH in report.candidates[0].case_path
    assert _tree_snapshot(staging_root) == before
