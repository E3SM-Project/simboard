"""Tests for the NERSC archive ingestion runner script."""

import json
import logging
import runpy
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from app.api.version import API_BASE
from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
)
from app.scripts.ingestion import nersc_archive_ingestor as ingestor_module
from app.scripts.ingestion.nersc_archive_ingestor import (
    CaseScanResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _build_case_path_filter,
    _build_case_scan_results,
    _build_config_from_env,
    _build_ingestion_candidates,
    _build_state_endpoint_url,
    _build_walk_dir_filter,
    _case_state_processed_ids,
    _discover_case_executions,
    _fetch_ingestion_state,
    _fresh_state,
    _ingest_case_with_retries,
    _is_transient_status,
    _log_event,
    _log_startup_configuration,
    _normalize_remote_state,
    _normalized_api_base_url,
    _parse_bool,
    _parse_optional_int,
    _post_ingestion_request,
    _record_successful_case,
    _render_log_value,
    _run_ingestor,
    _validate_execution_dir,
)


@pytest.fixture(autouse=True)
def _stub_remote_state(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    monkeypatch.setattr(
        ingestor_module,
        "_post_discovery_results_request",
        lambda *args, **kwargs: {"status_code": 201, "body": {}},
    )


def test_discover_case_executions_skips_incomplete_runs(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    complete_exec = case_dir / "100.1-1"
    incomplete_exec = case_dir / "101.1-1"

    complete_exec.mkdir(parents=True)
    incomplete_exec.mkdir(parents=True)

    def fake_locator(execution_dir: str) -> dict[str, str]:
        if execution_dir.endswith("101.1-1"):
            raise FileNotFoundError("missing required files")
        return {}

    grouped = _discover_case_executions(archive_root, metadata_locator=fake_locator)

    assert list(grouped.values()) == [["100.1-1"]]


def test_discover_case_executions_skips_unreadable_execution_dirs(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    complete_exec = case_dir / "100.1-1"
    unreadable_exec = case_dir / "101.1-1"

    complete_exec.mkdir(parents=True)
    unreadable_exec.mkdir(parents=True)

    stats = ingestor_module._new_discovery_stats()

    def fake_locator(execution_dir: str) -> dict[str, str]:
        if execution_dir.endswith("101.1-1"):
            raise PermissionError("permission denied")
        return {}

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=fake_locator,
        stats=stats,
    )

    assert list(grouped.values()) == [["100.1-1"]]
    assert stats["execution_dirs_scanned"] == 2
    assert stats["execution_dirs_accepted"] == 1
    assert stats["skipped_incomplete"] == 0
    assert stats["skipped_invalid"] == 0


def test_discover_case_executions_tracks_rejected_only_cases_for_logging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    total_skips = 22
    for index in range(total_skips):
        (archive_root / "case_a" / f"{100 + index}.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    case_collection_data: dict[str, ingestor_module.CaseCollectionLogData] = {}
    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: (_ for _ in ()).throw(FileNotFoundError("missing")),
        case_collection_data=case_collection_data,
    )

    assert grouped == {}
    assert logged_events[0] == (
        "archive_scan_started",
        {"scan_mode": "staging", "archive_root": str(archive_root)},
    )
    assert logged_events[1][0] == "archive_scan_completed"
    assert logged_events[1][1]["archive_root"] == str(archive_root)
    assert logged_events[1][1]["discovered_cases"] == 0
    case_log = case_collection_data[str((archive_root / "case_a").resolve())]
    assert case_log.execution_count_total == total_skips
    assert case_log.valid_execution_ids == set()
    assert sorted(
        decision.execution_id for decision in case_log.rejected_decisions
    ) == [f"{100 + index}.1-1" for index in range(total_skips)]
    assert {decision.detail for decision in case_log.rejected_decisions} == {"missing"}


def test_discover_case_executions_logs_scan_progress(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    for index in range(3):
        (archive_root / f"case_{index}" / f"{100 + index}.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(ingestor_module, "DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES", 2)

    grouped = _discover_case_executions(archive_root, metadata_locator=lambda *_: {})

    assert len(grouped) == 3

    archive_root_path = str(archive_root)
    start_events = [
        fields for event, fields in logged_events if event == "archive_scan_started"
    ]
    progress_events = [
        fields for event, fields in logged_events if event == "archive_scan_progress"
    ]
    completed_events = [
        fields for event, fields in logged_events if event == "archive_scan_completed"
    ]

    assert start_events == [{"scan_mode": "staging", "archive_root": archive_root_path}]
    assert len(progress_events) == 3
    assert progress_events[0]["scan_mode"] == "staging"
    assert progress_events[0]["archive_root"] == archive_root_path
    assert progress_events[0]["current_dir"].startswith(f"{archive_root_path}/case_")
    assert progress_events[0]["directories_visited"] == 2
    assert progress_events[0]["discovered_cases"] == 1
    assert progress_events[0]["execution_dirs_scanned"] == 1
    assert progress_events[0]["execution_dirs_accepted"] == 1
    assert progress_events[0]["rejected_existing_execution_ids"] == 0
    assert progress_events[1]["scan_mode"] == "staging"
    assert progress_events[1]["archive_root"] == archive_root_path
    assert progress_events[1]["current_dir"].startswith(f"{archive_root_path}/case_")
    assert progress_events[1]["directories_visited"] == 4
    assert progress_events[1]["discovered_cases"] == 2
    assert progress_events[1]["execution_dirs_scanned"] == 2
    assert progress_events[1]["execution_dirs_accepted"] == 2
    assert progress_events[1]["rejected_existing_execution_ids"] == 0
    assert progress_events[2]["scan_mode"] == "staging"
    assert progress_events[2]["archive_root"] == archive_root_path
    assert progress_events[2]["current_dir"].startswith(f"{archive_root_path}/case_")
    assert progress_events[2]["directories_visited"] == 6
    assert progress_events[2]["discovered_cases"] == 3
    assert progress_events[2]["execution_dirs_scanned"] == 3
    assert progress_events[2]["execution_dirs_accepted"] == 3
    assert progress_events[2]["rejected_existing_execution_ids"] == 0

    assert len(completed_events) == 1
    assert completed_events[0]["scan_mode"] == "staging"
    assert completed_events[0]["archive_root"] == archive_root_path
    assert completed_events[0]["current_dir"].startswith(f"{archive_root_path}/case_")
    assert completed_events[0]["directories_visited"] == 7
    assert completed_events[0]["discovered_cases"] == 3
    assert completed_events[0]["execution_dirs_scanned"] == 3
    assert completed_events[0]["execution_dirs_accepted"] == 3
    assert completed_events[0]["rejected_existing_execution_ids"] == 0


def test_discover_case_executions_skips_previously_processed_archive_ids(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    case_dir = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "COMPLETED"
        / "user_a"
        / "case_a"
    )
    existing_exec = case_dir / "100.1-1"
    new_exec = case_dir / "101.1-1"
    existing_exec.mkdir(parents=True)
    new_exec.mkdir(parents=True)

    locator_calls: list[str] = []
    discovery_results: list[ingestor_module.ExecutionDiscoveryResult] = []
    stats = ingestor_module._new_discovery_stats()
    processed_ids_by_key = ingestor_module._build_processed_ids_by_key(
        {
            "cases": {
                "/performance_archive/user_a/case_a": {
                    "processed_execution_ids": ["100.1-1"],
                }
            }
        },
        scan_mode="archive",
    )

    def fake_locator(execution_dir: str) -> dict[str, str]:
        locator_calls.append(execution_dir)
        return {}

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=fake_locator,
        stats=stats,
        walk_dir_filter=_build_walk_dir_filter(
            IngestorConfig(
                api_base_url="http://backend:8000",
                api_token="token",
                archive_root=archive_root,
                machine_name="perlmutter",
                dry_run=True,
                max_cases_per_run=None,
                max_attempts=1,
                request_timeout_seconds=30,
                scan_mode="archive",
            )
        ),
        scan_mode="archive",
        processed_ids_by_key=processed_ids_by_key,
        discovery_results=discovery_results,
    )

    assert grouped == {str(case_dir.resolve()): ["101.1-1"]}
    assert stats["execution_dirs_scanned"] == 1
    assert stats["execution_dirs_accepted"] == 1
    assert stats["rejected_existing_execution_ids"] == 1
    assert locator_calls == [str(new_exec)]
    assert [result.execution_id for result in discovery_results] == ["101.1-1"]


def test_run_ingestor_logs_case_grouped_outcomes_for_state_and_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    case_a = archive_root / "case_a"
    case_b = archive_root / "case_b"
    (case_a / "100.1-1").mkdir(parents=True)
    (case_a / "101.1-1").mkdir(parents=True)
    (case_b / "200.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: {
            "cases": {
                str(case_a.resolve()): {"processed_execution_ids": ["100.1-1"]},
            }
        },
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=1,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    decisions = [
        fields
        for event, fields in logged_events
        if event == "execution_collection_decision"
    ]
    case_begins = [
        fields for event, fields in logged_events if event == "case_collection_begin"
    ]
    case_summaries = [
        fields for event, fields in logged_events if event == "case_collection_summary"
    ]
    case_block_events = [
        (event, fields)
        for event, fields in logged_events
        if event
        in {
            "case_collection_begin",
            "execution_collection_decision",
            "case_collection_summary",
        }
    ]

    assert exit_code == 0
    assert case_block_events == [
        (
            "case_collection_begin",
            {
                "case": "case_a",
                "execution_count_total": 2,
                "execution_count_valid": 1,
                "execution_count_rejected_incomplete": 0,
                "execution_count_rejected_invalid": 0,
                "execution_count_transient": 0,
                "execution_count_existing": 1,
                "execution_count_new": 1,
                "execution_count_selected_new": 1,
                "execution_count_deferred": 0,
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_a",
                "decision": "rejected",
                "execution_id": "100.1-1",
                "reason": "already_processed",
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_a",
                "decision": "accepted",
                "execution_id": "101.1-1",
                "reason": "new_execution",
            },
        ),
        (
            "case_collection_summary",
            {
                "case": "case_a",
                "accepted": 1,
                "rejected_existing": 1,
                "rejected_incomplete": 0,
                "rejected_invalid": 0,
                "transient": 0,
                "deferred": 0,
            },
        ),
        (
            "case_collection_begin",
            {
                "case": "case_b",
                "execution_count_total": 1,
                "execution_count_valid": 1,
                "execution_count_rejected_incomplete": 0,
                "execution_count_rejected_invalid": 0,
                "execution_count_transient": 0,
                "execution_count_existing": 0,
                "execution_count_new": 1,
                "execution_count_selected_new": 0,
                "execution_count_deferred": 1,
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_b",
                "decision": "deferred",
                "execution_id": "200.1-1",
                "reason": "max_cases_per_run",
            },
        ),
        (
            "case_collection_summary",
            {
                "case": "case_b",
                "accepted": 0,
                "rejected_existing": 0,
                "rejected_incomplete": 0,
                "rejected_invalid": 0,
                "transient": 0,
                "deferred": 1,
            },
        ),
    ]
    assert decisions == [
        {
            "case": "case_a",
            "decision": "rejected",
            "execution_id": "100.1-1",
            "reason": "already_processed",
        },
        {
            "case": "case_a",
            "decision": "accepted",
            "execution_id": "101.1-1",
            "reason": "new_execution",
        },
        {
            "case": "case_b",
            "decision": "deferred",
            "execution_id": "200.1-1",
            "reason": "max_cases_per_run",
        },
    ]
    assert len(case_begins) == 2
    assert len(case_summaries) == 2
    scan_completed = [
        fields for event, fields in logged_events if event == "scan_completed"
    ][0]
    dry_run_completed = [
        fields for event, fields in logged_events if event == "dry_run_completed"
    ][0]

    for payload in (scan_completed, dry_run_completed):
        assert payload["submission_qualified_cases"] == 2
        assert payload["selected_submission_cases"] == 1
    assert scan_completed["rejected_existing_execution_ids"] == 1
    assert scan_completed["scan_mode"] == "staging"


def test_build_ingestion_candidates_is_idempotent() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/performance_archive/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = _fresh_state()

    first_candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
    )
    assert len(first_candidates) == 1
    assert first_candidates[0].new_execution_ids == ["100.1-1"]

    _record_successful_case(state, first_candidates[0])

    second_candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
    )
    assert second_candidates == []

    updated_scan_results = [
        CaseScanResult(
            case_path="/performance_archive/case_a",
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-2",
        )
    ]

    third_candidates = _build_ingestion_candidates(
        updated_scan_results,
        state,
        max_cases_per_run=None,
    )
    assert len(third_candidates) == 1
    assert third_candidates[0].new_execution_ids == ["101.1-1"]


def test_build_ingestion_candidates_dedupes_staging_mount_and_host_paths() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/global/cfs/cdirs/e3sm/performance_archive/user_a/case_a",
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="staging",
    )

    assert len(candidates) == 1
    assert candidates[0].case_path == (
        "/global/cfs/cdirs/e3sm/performance_archive/user_a/case_a"
    )
    assert candidates[0].new_execution_ids == ["101.1-1"]


def test_build_ingestion_candidates_dedupes_staging_host_and_mount_paths() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/performance_archive/user_a/case_a",
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = {
        "cases": {
            "/global/cfs/cdirs/e3sm/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="staging",
    )

    assert len(candidates) == 1
    assert candidates[0].case_path == "/performance_archive/user_a/case_a"
    assert candidates[0].new_execution_ids == ["101.1-1"]


def test_build_ingestion_candidates_keeps_raw_staging_paths_without_root_basename() -> (
    None
):
    scan_results = [
        CaseScanResult(
            case_path="/tmp/local_archive/user_a/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="staging",
    )

    assert len(candidates) == 1
    assert candidates[0].new_execution_ids == ["100.1-1"]


def test_build_ingestion_candidates_dedupes_archive_snapshots_against_staging_state() -> (
    None
):
    scan_results = [
        CaseScanResult(
            case_path=(
                "/archive/2026-05/performance_archive_2026_05_22_08_01_32/"
                "COMPLETED/user_a/case_a"
            ),
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        ),
        CaseScanResult(
            case_path=(
                "/archive/2026-06/performance_archive_2026_06_01_08_01_32/user_a/case_a"
            ),
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-2",
        ),
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="archive",
    )

    assert len(candidates) == 1
    assert candidates[0].case_path.endswith("/user_a/case_a")
    assert candidates[0].new_execution_ids == ["101.1-1"]


def test_build_ingestion_candidates_does_not_strip_live_queue_state_dirs() -> None:
    scan_results = [
        CaseScanResult(
            case_path=(
                "/archive/2026-05/performance_archive_2026_05_22_08_01_32/"
                "PENDING/user_a/case_a"
            ),
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="archive",
    )

    assert len(candidates) == 1
    assert candidates[0].case_path.endswith("/PENDING/user_a/case_a")
    assert candidates[0].new_execution_ids == ["100.1-1", "101.1-1"]


def test_build_ingestion_candidates_does_not_strip_non_completed_archive_status_dir() -> (
    None
):
    scan_results = [
        CaseScanResult(
            case_path=(
                "/archive/2026-05/performance_archive_2026_05_22_08_01_32/"
                "STOPPED/user_a/case_a"
            ),
            execution_ids=["100.1-1", "101.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="archive",
    )

    assert len(candidates) == 1
    assert candidates[0].case_path.endswith("/STOPPED/user_a/case_a")
    assert candidates[0].new_execution_ids == ["100.1-1", "101.1-1"]


def test_build_ingestion_candidates_keeps_distinct_users_without_snapshot_dir() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/archive/2026-05/user_a/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        ),
        CaseScanResult(
            case_path="/archive/2026-06/user_b/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-2",
        ),
    ]
    state = {
        "cases": {
            "/performance_archive/user_a/case_a": {
                "processed_execution_ids": ["100.1-1"],
            }
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
        scan_mode="archive",
    )

    assert [candidate.case_path for candidate in candidates] == [
        "/archive/2026-06/user_b/case_a"
    ]
    assert candidates[0].new_execution_ids == ["100.1-1"]


def test_discover_case_executions_filters_archive_year_range(tmp_path: Path) -> None:
    archive_root = tmp_path / "old_perf"
    included_case = (
        archive_root
        / "2025-02"
        / "performance_archive_2025_02_01_00_00_00"
        / "user_a"
        / "case_a"
        / "100.1-1"
    )
    excluded_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_31_00_00_00"
        / "user_b"
        / "case_b"
        / "200.1-1"
    )
    included_case.mkdir(parents=True)
    excluded_case.mkdir(parents=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-02",
        archive_year_end="2025-02",
    )
    stats = ingestor_module._new_discovery_stats()

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: {},
        stats=stats,
        case_path_filter=_build_case_path_filter(config),
        walk_dir_filter=_build_walk_dir_filter(config),
        scan_mode="archive",
    )

    assert stats["execution_dirs_scanned"] == 1
    assert list(grouped.keys()) == [str(included_case.parent.resolve())]
    assert list(grouped.values()) == [["100.1-1"]]


def test_discover_case_executions_rejects_archive_year_range_under_non_year_root(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    included_case = (
        archive_root
        / "OLD"
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "case_a"
        / "100.1-1"
    )
    excluded_case = (
        archive_root
        / "OLD"
        / "2024-12"
        / "performance_archive_2024_12_31_00_00_00"
        / "case_b"
        / "200.1-1"
    )
    included_case.mkdir(parents=True)
    excluded_case.mkdir(parents=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
        archive_year_end="2025-01",
    )

    with pytest.raises(
        ValueError,
        match="ARCHIVE_YEAR_START and ARCHIVE_YEAR_END require archive paths",
    ):
        _discover_case_executions(
            archive_root,
            metadata_locator=lambda *_: {},
            case_path_filter=_build_case_path_filter(config),
            walk_dir_filter=_build_walk_dir_filter(config),
            scan_mode="archive",
        )


def test_discover_case_executions_ignores_root_symlink_for_year_filter(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    target_dir = tmp_path / "linked_perf"
    (target_dir / "case_a" / "100.1-1").mkdir(parents=True)
    archive_root.mkdir()
    (archive_root / "README.txt").write_text("marker\n")
    (archive_root / "linked").symlink_to(target_dir, target_is_directory=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
        archive_year_end="2025-01",
    )
    stats = ingestor_module._new_discovery_stats()

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: {},
        stats=stats,
        case_path_filter=_build_case_path_filter(config),
        walk_dir_filter=_build_walk_dir_filter(config),
        scan_mode="archive",
    )

    assert grouped == {}
    assert stats["execution_dirs_scanned"] == 0


def test_discover_case_executions_ignores_non_completed_archive_status_dirs(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    completed_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "COMPLETED"
        / "user_a"
        / "case_a"
        / "100.1-1"
    )
    stopped_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "STOPPED"
        / "user_a"
        / "case_a"
        / "200.1-1"
    )
    pending_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "PENDING"
        / "user_a"
        / "case_a"
        / "300.1-1"
    )
    completed_case.mkdir(parents=True)
    stopped_case.mkdir(parents=True)
    pending_case.mkdir(parents=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start=None,
        archive_year_end=None,
    )
    stats = ingestor_module._new_discovery_stats()

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: {},
        stats=stats,
        walk_dir_filter=_build_walk_dir_filter(config),
        scan_mode="archive",
    )

    assert stats["execution_dirs_scanned"] == 1
    assert list(grouped.keys()) == [str(completed_case.parent.resolve())]
    assert list(grouped.values()) == [["100.1-1"]]


def test_discover_case_executions_ignores_non_year_root_dirs_without_year_filter(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    supported_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "user_a"
        / "case_a"
        / "100.1-1"
    )
    unsupported_case = (
        archive_root
        / "OLDER_ARCHIVES"
        / "performance_archive_cori_edison_acme_2019_08_13"
        / "user_b"
        / "case_b"
        / "200.1-1"
    )
    supported_case.mkdir(parents=True)
    unsupported_case.mkdir(parents=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start=None,
        archive_year_end=None,
    )
    stats = ingestor_module._new_discovery_stats()

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: {},
        stats=stats,
        walk_dir_filter=_build_walk_dir_filter(config),
        scan_mode="archive",
    )

    assert stats["execution_dirs_scanned"] == 1
    assert list(grouped.keys()) == [str(supported_case.parent.resolve())]
    assert list(grouped.values()) == [["100.1-1"]]


def test_discover_case_executions_skips_unsupported_layout_when_year_filtered(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "old_perf"
    unsupported_case = (
        archive_root
        / "OLDER_ARCHIVES"
        / "performance_archive_cori_edison_acme_2019_08_13"
        / "user_a"
        / "case_a"
        / "100.1-1"
    )
    supported_case = (
        archive_root
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "user_b"
        / "case_b"
        / "200.1-1"
    )
    unsupported_case.mkdir(parents=True)
    supported_case.mkdir(parents=True)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
        archive_year_end="2025-01",
    )
    stats = ingestor_module._new_discovery_stats()

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: {},
        stats=stats,
        case_path_filter=_build_case_path_filter(config),
        walk_dir_filter=_build_walk_dir_filter(config),
        scan_mode="archive",
    )

    assert stats["execution_dirs_scanned"] == 1
    assert list(grouped.keys()) == [str(supported_case.parent.resolve())]
    assert list(grouped.values()) == [["200.1-1"]]


def test_build_ingestion_candidates_handles_non_dict_case_state_and_limit() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/performance_archive/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        ),
        CaseScanResult(
            case_path="/performance_archive/case_b",
            execution_ids=["200.1-1"],
            fingerprint="fp-2",
        ),
    ]
    state = {
        "cases": {
            "/performance_archive/case_a": "invalid",
            "/performance_archive/case_b": {
                "processed_execution_ids": ["200.1-1"],
            },
        }
    }

    candidates = _build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=1,
    )

    assert len(candidates) == 1
    assert candidates[0].case_path == "/performance_archive/case_a"


def test_build_ingestion_candidates_handles_non_dict_cases_root() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/performance_archive/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        )
    ]

    candidates = _build_ingestion_candidates(
        scan_results,
        state={"cases": "invalid"},
        max_cases_per_run=None,
    )

    assert len(candidates) == 1
    assert candidates[0].new_execution_ids == ["100.1-1"]


def test_validate_execution_dir_treats_plain_file_not_found_as_transient(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()

    decision = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(FileNotFoundError("missing")),
        stats=stats,
    )

    assert decision is not None
    assert decision.to_log_fields() == {
        "case": str(case_dir.resolve()),
        "decision": "rejected",
        "execution_id": "100.1-1",
        "reason": "transient",
        "detail": "missing",
    }
    assert stats["skipped_incomplete"] == 0
    assert stats["rejected_incomplete_execution_ids"] == 0


def test_validate_execution_dir_counts_value_error_with_stats(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()

    validation_error = ArchiveValidationError([])
    validation_error.args = ("invalid",)
    decision = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(validation_error),
        stats=stats,
    )

    assert decision is not None
    assert decision.to_log_fields() == {
        "case": str(case_dir.resolve()),
        "decision": "rejected",
        "execution_id": "100.1-1",
        "reason": "invalid",
        "detail": "invalid",
    }
    assert stats["skipped_invalid"] == 1
    assert stats["rejected_invalid_execution_ids"] == 1


def test_build_case_scan_results_skips_empty_execution_lists() -> None:
    grouped = {
        "/performance_archive/case_a": [],
        "/performance_archive/case_b": ["200.1-1"],
    }

    results = _build_case_scan_results(grouped)

    assert [result.case_path for result in results] == ["/performance_archive/case_b"]


def test_ingest_case_with_retries_retries_transient_errors() -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    attempts: list[int] = []
    sleep_calls: list[float] = []

    def fake_post_request(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise IngestionRequestError(
                "temporary error",
                status_code=503,
                transient=True,
            )
        return {"status_code": 201, "body": {"created_count": 1, "errors": []}}

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="perlmutter",
        max_attempts=3,
        timeout_seconds=10,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert sleep_calls == [1]


def test_ingest_case_with_retries_does_not_retry_non_transient_errors() -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    call_count = 0

    def fake_post_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise IngestionRequestError(
            "bad request",
            status_code=400,
            transient=False,
        )

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="perlmutter",
        max_attempts=3,
        timeout_seconds=10,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is False
    assert result["attempts"] == 1
    assert call_count == 1


def test_run_ingestor_uses_remote_state_and_builds_expected_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    captured_calls: list[dict[str, str]] = []
    remote_state = _fresh_state()

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_calls.append(
            {
                "endpoint_url": endpoint_url,
                "api_token": api_token,
                "archive_path": archive_path,
                "machine_name": machine_name,
                "processed_execution_ids": ",".join(processed_execution_ids),
                "timeout_seconds": str(timeout_seconds),
            }
        )
        _record_successful_case(
            remote_state,
            IngestionCandidate(
                case_path=archive_path,
                execution_ids=["100.1-1"],
                new_execution_ids=["100.1-1"],
                fingerprint=ingestor_module._compute_case_fingerprint(["100.1-1"]),
            ),
        )
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: remote_state,
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token-123",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code_first = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )
    exit_code_second = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code_first == 0
    assert exit_code_second == 0
    assert len(captured_calls) == 1
    assert captured_calls[0] == {
        "endpoint_url": "http://backend:8000/api/v1/ingestions/from-path",
        "api_token": "token-123",
        "archive_path": str(case_dir.resolve()),
        "machine_name": "perlmutter",
        "processed_execution_ids": "100.1-1",
        "timeout_seconds": "30",
    }
    assert str(case_dir.resolve()) in remote_state["cases"]


def test_run_ingestor_submits_only_new_execution_ids_for_mixed_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "101.1-1").mkdir(parents=True)

    captured_processed_execution_ids: list[list[str]] = []
    remote_state = {
        "cases": {
            str(case_dir.resolve()): {"processed_execution_ids": ["100.1-1"]},
        }
    }

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_processed_execution_ids.append(processed_execution_ids)
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: remote_state,
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token-123",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code == 0
    assert captured_processed_execution_ids == [["101.1-1"]]
    assert remote_state["cases"][str(case_dir.resolve())][
        "processed_execution_ids"
    ] == [
        "100.1-1",
        "101.1-1",
    ]


def test_run_ingestor_submits_only_new_ids_when_state_uses_mount_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "101.1-1").mkdir(parents=True)

    captured_processed_execution_ids: list[list[str]] = []
    remote_state = {
        "cases": {
            "/performance_archive/case_a": {
                "processed_execution_ids": ["100.1-1"],
            },
        }
    }

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_processed_execution_ids.append(processed_execution_ids)
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: remote_state,
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token-123",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code == 0
    assert captured_processed_execution_ids == [["101.1-1"]]


def test_handle_ingest_run_returns_failure_when_case_ingestion_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    def fake_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("boom", status_code=503, transient=False)

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert exit_code == 1
    assert any(event == "case_ingestion_failed" for event, _ in logged_events)


def test_build_case_scan_results_is_deterministic() -> None:
    grouped = {
        "/performance_archive/case_b": ["200.1-1"],
        "/performance_archive/case_a": ["100.1-1", "101.1-1"],
    }

    results = _build_case_scan_results(grouped)

    assert [result.case_path for result in results] == [
        "/performance_archive/case_a",
        "/performance_archive/case_b",
    ]


def test_run_ingestor_dry_run_without_token_returns_config_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
    )

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)


def test_run_ingestor_without_token_returns_config_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)
    assert not any(event == "scan_completed" for event, _ in logged_events)


def test_run_ingestor_returns_failure_when_state_fetch_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            IngestionRequestError("boom", status_code=503, transient=True)
        ),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "state_fetch_failed" for event, _ in logged_events)
    assert not any(event == "scan_completed" for event, _ in logged_events)


def test_run_ingestor_returns_config_error_for_unsupported_archive_year_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "old_perf"
    (archive_root / "OLD" / "user_a" / "case_a" / "100.1-1").mkdir(parents=True)
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
        archive_year_end="2025-01",
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)
    assert not any(event == "scan_completed" for event, _ in logged_events)


def test_run_ingestor_fails_on_unexpected_scan_value_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module,
        "_scan_archive",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert _run_ingestor(config, metadata_locator=lambda *_: {}) == 1

    assert ("archive_scan_failed", {"error": "ValueError: boom"}) in logged_events
    assert not any(event == "configuration_error" for event, _ in logged_events)


def test_run_ingestor_missing_archive_root_returns_failure_without_ingestion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing_archive_root = tmp_path / "missing-archive"
    post_calls = 0
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_post_request(*args, **kwargs):
        nonlocal post_calls
        post_calls += 1
        return {"status_code": 201, "body": {"created_count": 1, "errors": []}}

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=missing_archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        post_request_fn=fake_post_request,
        sleep_fn=lambda *_: None,
    )

    assert exit_code == 1
    assert post_calls == 0
    assert any(event == "archive_root_missing" for event, _ in logged_events)


def test_run_ingestor_unreadable_archive_root_returns_config_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    logged_events: list[tuple[str, dict[str, Any]]] = []
    original_iterdir = Path.iterdir

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    def fake_iterdir(self: Path):
        if self.resolve() == archive_root.resolve():
            raise PermissionError("permission denied")
        return original_iterdir(self)

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
        archive_year_end="2025-01",
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)
    assert not any(event == "scan_completed" for event, _ in logged_events)


def test_dry_run_candidate_suppression_event_emitted_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    total_cases = ingestor_module.MAX_DRY_RUN_CANDIDATE_LOGS + 5
    for index in range(total_cases):
        (archive_root / f"case_{index:03d}" / "100.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    suppression_events = [
        fields
        for event, fields in logged_events
        if event == "dry_run_candidate_logs_suppressed"
    ]
    candidate_events = [
        fields for event, fields in logged_events if event == "dry_run_candidate"
    ]
    assert exit_code == 0
    assert len(suppression_events) == 1
    assert candidate_events[0]["case"] == "case_000"
    assert "case_path" not in candidate_events[0]
    assert suppression_events[0]["suppressed_count"] == 5
    assert (
        suppression_events[0]["detail_log_limit"]
        == ingestor_module.MAX_DRY_RUN_CANDIDATE_LOGS
    )


def test_completion_events_include_summary_counters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dry_archive = tmp_path / "dry_archive"
    ingest_archive = tmp_path / "ingest_archive"
    (dry_archive / "case_dry" / "100.1-1").mkdir(parents=True)
    (ingest_archive / "case_ingest" / "100.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    dry_run_config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=dry_archive,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )
    ingest_config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=ingest_archive,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    _run_ingestor(dry_run_config, metadata_locator=lambda *_: {})

    def fake_ingest_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    _run_ingestor(
        ingest_config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_ingest_post_request,
    )

    dry_run_completed = [
        fields for event, fields in logged_events if event == "dry_run_completed"
    ][0]
    run_completed = [
        fields for event, fields in logged_events if event == "run_completed"
    ][0]
    dry_run_summary_counts = [
        fields for event, fields in logged_events if event == "dry_run_summary_counts"
    ][0]
    dry_run_summary_candidates = [
        fields
        for event, fields in logged_events
        if event == "dry_run_summary_candidates"
    ][0]
    run_summary_counts = [
        fields for event, fields in logged_events if event == "run_summary_counts"
    ][0]
    run_summary_outcomes = [
        fields for event, fields in logged_events if event == "run_summary_outcomes"
    ][0]

    for payload in (dry_run_completed, run_completed):
        assert isinstance(payload["submission_qualified_cases"], int)
        assert isinstance(payload["selected_submission_cases"], int)
        assert isinstance(payload["execution_dirs_scanned"], int)
        assert isinstance(payload["execution_dirs_accepted"], int)
        assert isinstance(payload["skipped_incomplete"], int)
        assert isinstance(payload["skipped_invalid"], int)
        assert isinstance(payload["accepted_execution_ids"], int)
        assert isinstance(payload["rejected_existing_execution_ids"], int)
        assert isinstance(payload["rejected_incomplete_execution_ids"], int)
        assert isinstance(payload["rejected_invalid_execution_ids"], int)
        assert isinstance(payload["deferred_execution_ids"], int)

    assert dry_run_summary_counts["mode"] == "dry-run"
    assert isinstance(dry_run_summary_counts["discovered_cases"], int)
    assert isinstance(dry_run_summary_counts["submission_qualified_cases"], int)
    assert isinstance(dry_run_summary_counts["selected_submission_cases"], int)
    assert isinstance(dry_run_summary_counts["execution_dirs_scanned"], int)
    assert isinstance(dry_run_summary_counts["execution_dirs_accepted"], int)
    assert isinstance(dry_run_summary_counts["skipped_incomplete"], int)
    assert isinstance(dry_run_summary_counts["skipped_invalid"], int)

    assert isinstance(dry_run_summary_candidates["accepted_execution_ids"], int)
    assert isinstance(
        dry_run_summary_candidates["rejected_existing_execution_ids"], int
    )
    assert isinstance(
        dry_run_summary_candidates["rejected_incomplete_execution_ids"], int
    )
    assert isinstance(dry_run_summary_candidates["rejected_invalid_execution_ids"], int)
    assert isinstance(dry_run_summary_candidates["deferred_execution_ids"], int)
    assert isinstance(dry_run_summary_candidates["candidate_logs_emitted"], int)
    assert isinstance(dry_run_summary_candidates["candidate_logs_suppressed"], int)

    assert run_summary_counts["mode"] == "ingest"
    assert isinstance(run_summary_counts["scanned_cases"], int)
    assert isinstance(run_summary_counts["submission_qualified_cases"], int)
    assert isinstance(run_summary_counts["selected_submission_cases"], int)
    assert isinstance(run_summary_counts["execution_dirs_scanned"], int)
    assert isinstance(run_summary_counts["execution_dirs_accepted"], int)
    assert isinstance(run_summary_counts["skipped_incomplete"], int)
    assert isinstance(run_summary_counts["skipped_invalid"], int)

    assert isinstance(run_summary_outcomes["success_count"], int)
    assert isinstance(run_summary_outcomes["failure_count"], int)
    assert isinstance(run_summary_outcomes["accepted_execution_ids"], int)
    assert isinstance(run_summary_outcomes["rejected_existing_execution_ids"], int)
    assert isinstance(run_summary_outcomes["rejected_incomplete_execution_ids"], int)
    assert isinstance(run_summary_outcomes["rejected_invalid_execution_ids"], int)
    assert isinstance(run_summary_outcomes["deferred_execution_ids"], int)


def test_build_config_from_env_parses_valid_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "http://example")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("PERF_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("MACHINE_NAME", "pm")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("MAX_CASES_PER_RUN", "5")
    monkeypatch.setenv("MAX_ATTEMPTS", "4")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "90")

    config = _build_config_from_env()

    assert config.api_base_url == "http://example"
    assert config.api_token == "token"
    assert config.archive_root == (tmp_path / "archive").resolve()
    assert config.machine_name == "pm"
    assert config.dry_run is True
    assert config.max_cases_per_run == 5
    assert config.max_attempts == 4
    assert config.request_timeout_seconds == 90
    assert config.scan_mode == "staging"
    assert config.archive_year_start is None
    assert config.archive_year_end is None


def test_build_config_from_env_parses_archive_mode_and_year_range(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("SCAN_MODE", "archive")
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", str(tmp_path / "old"))
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2023")
    monkeypatch.setenv("ARCHIVE_YEAR_END", "2025")

    config = _build_config_from_env()

    assert config.scan_mode == "archive"
    assert config.archive_root == (tmp_path / "old").resolve()
    assert config.archive_year_start == "2023-01"
    assert config.archive_year_end == "2025-12"


def test_build_config_from_env_parses_archive_mode_and_month_range(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("SCAN_MODE", "archive")
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", str(tmp_path / "old"))
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2023-06")
    monkeypatch.setenv("ARCHIVE_YEAR_END", "2025-02")

    config = _build_config_from_env()

    assert config.scan_mode == "archive"
    assert config.archive_root == (tmp_path / "old").resolve()
    assert config.archive_year_start == "2023-06"
    assert config.archive_year_end == "2025-02"


@pytest.mark.parametrize(
    ("env_name", "env_value", "message"),
    [
        ("MAX_CASES_PER_RUN", "0", "MAX_CASES_PER_RUN must be greater than 0"),
        ("MAX_ATTEMPTS", "0", "MAX_ATTEMPTS must be greater than 0"),
        (
            "REQUEST_TIMEOUT_SECONDS",
            "0",
            "REQUEST_TIMEOUT_SECONDS must be greater than 0",
        ),
        (
            "ARCHIVE_YEAR_START",
            "2025",
            "ARCHIVE_YEAR_START and ARCHIVE_YEAR_END require SCAN_MODE=archive",
        ),
    ],
)
def test_build_config_from_env_rejects_invalid_positive_values(
    monkeypatch,
    env_name: str,
    env_value: str,
    message: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    if env_name == "ARCHIVE_YEAR_START":
        monkeypatch.delenv("SCAN_MODE", raising=False)

    with pytest.raises(ValueError, match=message):
        _build_config_from_env()


def test_build_config_from_env_rejects_archive_year_range_inverted(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SCAN_MODE", "archive")
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2026-02")
    monkeypatch.setenv("ARCHIVE_YEAR_END", "2025-12")

    with pytest.raises(
        ValueError,
        match="ARCHIVE_YEAR_START must be less than or equal to ARCHIVE_YEAR_END",
    ):
        _build_config_from_env()


@pytest.mark.parametrize(
    ("env_name", "env_value", "message"),
    [
        (
            "ARCHIVE_YEAR_START",
            "2025-13",
            "ARCHIVE_YEAR_START month must be between 01 and 12",
        ),
        (
            "ARCHIVE_YEAR_END",
            "2025-6",
            "ARCHIVE_YEAR_END must use YYYY or YYYY-MM format",
        ),
    ],
)
def test_build_config_from_env_rejects_invalid_archive_bound_formats(
    monkeypatch,
    env_name: str,
    env_value: str,
    message: str,
) -> None:
    monkeypatch.setenv("SCAN_MODE", "archive")
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(ValueError, match=message):
        _build_config_from_env()


def test_main_returns_configuration_error_when_config_build_fails(monkeypatch) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(
        ingestor_module,
        "_build_config_from_env",
        lambda: (_ for _ in ()).throw(ValueError("bad config")),
    )
    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    exit_code = ingestor_module.main()

    assert exit_code == 1
    assert logged_events == [("configuration_error", {"error": "bad config"})]


def test_main_logs_run_started_and_finished(monkeypatch, tmp_path: Path) -> None:
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=tmp_path,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_build_config_from_env", lambda: config)
    monkeypatch.setattr(ingestor_module, "_run_ingestor", lambda cfg: 0)
    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    monkeypatch.setattr(
        ingestor_module.time, "monotonic", lambda: 10.0 if not logged_events else 12.5
    )

    exit_code = ingestor_module.main()

    assert exit_code == 0
    assert logged_events[0][0] == "run_started"
    assert logged_events[-1][0] == "run_finished"
    assert logged_events[0][1]["scan_mode"] == "staging"
    assert logged_events[-1][1]["scan_mode"] == "staging"


def test_module_main_guard_exits_via_system_exit_on_configuration_error(
    monkeypatch,
) -> None:
    script_path = (
        Path(__file__).resolve().parents[3]
        / "app/scripts/ingestion/nersc_archive_ingestor.py"
    )
    monkeypatch.setenv("MAX_ATTEMPTS", "0")
    monkeypatch.setattr(logging.Logger, "info", lambda *args, **kwargs: None)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(script_path), run_name="__main__")

    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (None, True, True),
        ("yes", False, True),
        ("off", True, False),
        ("maybe", True, True),
    ],
)
def test_parse_bool(value: str | None, default: bool, expected: bool) -> None:
    assert _parse_bool(value, default=default) is expected


def test_parse_optional_int_handles_none_and_blank() -> None:
    assert _parse_optional_int(None) is None
    assert _parse_optional_int("   ") is None
    assert _parse_optional_int("7") == 7


def test_ingest_case_with_retries_uses_default_post_request_fn(monkeypatch) -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )
    captured: list[tuple[str, str, str, str, str, int]] = []

    def fake_post(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        processed_execution_ids: list[str],
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured.append(
            (
                endpoint_url,
                api_token,
                archive_path,
                machine_name,
                ",".join(processed_execution_ids),
                timeout_seconds,
            )
        )
        return {"status_code": 201, "body": {"created_count": 1}}

    monkeypatch.setattr(ingestor_module, "_post_ingestion_request", fake_post)

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=1,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
    )

    assert result["ok"] is True
    assert captured == [
        (
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/performance_archive/case_a",
            "pm",
            "100.1-1",
            5,
        )
    ]


def test_ingest_case_with_retries_normalizes_non_dict_body() -> None:
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )

    def fake_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        return {"status_code": 201, "body": "bad"}  # type: ignore[typeddict-item]

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=1,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result["ok"] is True
    assert result["body"] == {}


def test_ingest_case_with_retries_returns_exhausted_retries_when_zero_attempts() -> (
    None
):
    candidate = IngestionCandidate(
        case_path="/performance_archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )

    def fake_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        return {"status_code": 201, "body": {}}

    result = _ingest_case_with_retries(
        candidate,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        api_token="token",
        machine_name="pm",
        max_attempts=0,
        timeout_seconds=5,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )

    assert result == {
        "ok": False,
        "attempts": 0,
        "status_code": None,
        "body": None,
        "error": "Exhausted retries",
    }


class _FakeHttpResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeHttpError(urllib.error.HTTPError):
    def __init__(self, url: str, code: int, msg: str, body: bytes) -> None:
        super().__init__(url, code, msg, hdrs=Message(), fp=None)
        self._body = body

    def read(self, amt: int = -1) -> bytes:
        return self._body if amt == -1 else self._body[:amt]


def test_post_ingestion_request_success(monkeypatch) -> None:
    captured_request: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_request.append(request)
        assert timeout == 12
        return _FakeHttpResponse(201, json.dumps({"created_count": 1}))

    monkeypatch.setattr(ingestor_module.urllib.request, "urlopen", fake_urlopen)

    response = _post_ingestion_request(
        "http://backend:8000/api/v1/ingestions/from-path",
        "token",
        "/archive/case_a",
        "pm",
        processed_execution_ids=["100.1-1", "101.1-1"],
        timeout_seconds=12,
    )

    assert response == {"status_code": 201, "body": {"created_count": 1}}
    assert captured_request[0].headers["Authorization"] == "Bearer token"
    request_body = captured_request[0].data
    assert isinstance(request_body, bytes)
    assert json.loads(request_body.decode("utf-8")) == {
        "archive_path": "/archive/case_a",
        "machine_name": "pm",
        "processed_execution_ids": ["100.1-1", "101.1-1"],
    }


def test_post_ingestion_request_handles_http_error(monkeypatch) -> None:
    request = urllib.request.Request("http://example.com")
    error = _FakeHttpError(
        request.full_url,
        503,
        "Service Unavailable",
        b"retry later",
    )

    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(IngestionRequestError) as exc_info:
        _post_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/archive/case_a",
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.transient is True


def test_post_ingestion_request_handles_url_error(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("network down")
        ),
    )

    with pytest.raises(IngestionRequestError, match="URL error: network down"):
        _post_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/archive/case_a",
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


def test_post_ingestion_request_handles_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    with pytest.raises(IngestionRequestError, match="Request timed out"):
        _post_ingestion_request(
            "http://backend:8000/api/v1/ingestions/from-path",
            "token",
            "/archive/case_a",
            "pm",
            processed_execution_ids=["100.1-1"],
            timeout_seconds=12,
        )


def test_is_transient_status() -> None:
    assert _is_transient_status(503) is True
    assert _is_transient_status(400) is False


def test_normalize_remote_state_rejects_non_dict_payload() -> None:
    with pytest.raises(
        IngestionRequestError,
        match="Invalid ingestion state response payload.",
    ):
        _normalize_remote_state([])  # type: ignore[arg-type]


def test_normalize_remote_state_sanitizes_cases() -> None:
    state = _normalize_remote_state(
        {
            "cases": {
                "/archive/case_a": {
                    "processed_execution_ids": ["101.1-1", "100.1-1", "100.1-1"],
                },
                "/archive/case_b": {"processed_execution_ids": "bad"},
                123: {"processed_execution_ids": ["skip"]},
            }
        }
    )

    assert state["cases"]["/archive/case_a"]["processed_execution_ids"] == [
        "100.1-1",
        "101.1-1",
    ]
    assert state["cases"]["/archive/case_b"]["processed_execution_ids"] == []
    assert "/archive/case_a" in state["cases"]
    assert 123 not in state["cases"]


def test_fetch_ingestion_state_success(monkeypatch) -> None:
    captured_request: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_request.append(request)
        assert timeout == 12
        return _FakeHttpResponse(
            200,
            json.dumps(
                {
                    "machine_name": "pm",
                    "cases": {
                        "/archive/case_a": {
                            "processed_execution_ids": ["100.1-1"],
                            "fingerprint": "fp-1",
                        }
                    },
                }
            ),
        )

    monkeypatch.setattr(ingestor_module.urllib.request, "urlopen", fake_urlopen)

    state = _fetch_ingestion_state(
        "http://backend:8000/api/v1/ingestions/state",
        "token",
        "pm",
        timeout_seconds=12,
    )

    assert state["cases"]["/archive/case_a"]["processed_execution_ids"] == ["100.1-1"]
    assert "machine_name=pm" in captured_request[0].full_url
    assert captured_request[0].headers["Authorization"] == "Bearer token"


def test_fetch_ingestion_state_handles_http_error(monkeypatch) -> None:
    request = urllib.request.Request("http://example.com")
    error = _FakeHttpError(
        request.full_url,
        503,
        "Service Unavailable",
        b"retry later",
    )

    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(IngestionRequestError) as exc_info:
        _fetch_ingestion_state(
            "http://backend:8000/api/v1/ingestions/state",
            "token",
            "pm",
            timeout_seconds=12,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.transient is True


def test_fetch_ingestion_state_handles_url_error(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("network down")
        ),
    )

    with pytest.raises(IngestionRequestError, match="URL error: network down"):
        _fetch_ingestion_state(
            "http://backend:8000/api/v1/ingestions/state",
            "token",
            "pm",
            timeout_seconds=12,
        )


def test_fetch_ingestion_state_handles_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    with pytest.raises(IngestionRequestError, match="Request timed out"):
        _fetch_ingestion_state(
            "http://backend:8000/api/v1/ingestions/state",
            "token",
            "pm",
            timeout_seconds=12,
        )


def test_fetch_ingestion_state_handles_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestor_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _FakeHttpResponse(200, "{invalid"),
    )

    with pytest.raises(IngestionRequestError, match="Invalid JSON response:"):
        _fetch_ingestion_state(
            "http://backend:8000/api/v1/ingestions/state",
            "token",
            "pm",
            timeout_seconds=12,
        )


def test_record_successful_case_replaces_non_dict_cases() -> None:
    state: dict[str, Any] = {"cases": []}
    candidate = IngestionCandidate(
        case_path="/archive/case_a",
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fp-1",
    )

    _record_successful_case(state, candidate)

    assert state["cases"]["/archive/case_a"]["fingerprint"] == "fp-1"


def test_case_state_processed_ids_ignores_non_list() -> None:
    assert _case_state_processed_ids({"processed_execution_ids": "bad"}) == set()


def test_normalize_remote_state_replaces_non_dict_cases_root() -> None:
    state = _normalize_remote_state({"cases": []})

    assert state["cases"] == {}


def test_build_state_endpoint_url() -> None:
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=Path("/archive"),
        machine_name="pm",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert _build_state_endpoint_url(config) == (
        "http://backend:8000/api/v1/ingestions/state"
    )


def test_normalized_api_base_url_handles_existing_api_base() -> None:
    base_url = f"http://backend:8000{API_BASE}"
    assert _normalized_api_base_url(base_url) == base_url
    assert _normalized_api_base_url("http://backend:8000/") == (
        f"http://backend:8000{API_BASE}"
    )


def test_render_log_value_formats_values() -> None:
    assert _render_log_value("plain-value") == "plain-value"
    assert _render_log_value("value with space") == '"value with space"'
    assert _render_log_value({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'


def test_discovery_results_capture_typed_outcomes_but_not_transient_errors(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    for execution_id in ("100.1-1", "101.1-1", "102.1-1", "103.1-1"):
        (case_dir / execution_id).mkdir(parents=True)
    results: list[ingestor_module.ExecutionDiscoveryResult] = []

    def locator(path: str) -> object:
        if path.endswith("101.1-1"):
            raise IncompleteArchiveError([])
        if path.endswith("102.1-1"):
            raise ArchiveValidationError([])
        if path.endswith("103.1-1"):
            raise PermissionError("temporary")
        return {}

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=locator,
        discovery_results=results,
    )

    assert grouped == {str(case_dir.resolve()): ["100.1-1"]}
    assert sorted((result.execution_id, result.outcome) for result in results) == [
        ("100.1-1", "accepted"),
        ("101.1-1", "rejected_incomplete"),
        ("102.1-1", "rejected_invalid"),
    ]


def test_stored_accepted_discovery_result_bypasses_validation(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: pytest.fail("validation should be bypassed"),
        discovery_results_by_key={(str(case_dir.resolve()), "100.1-1"): "accepted"},
    )

    assert grouped == {str(case_dir.resolve()): ["100.1-1"]}


def test_discovery_persistence_failure_prevents_ingestion(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    ingestion_calls: list[object] = []

    def fail_persistence(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("unavailable", status_code=503, transient=False)

    def record_ingestion(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        ingestion_calls.append(args)
        return {"status_code": 201, "body": {}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        post_request_fn=record_ingestion,
        discovery_post_request_fn=fail_persistence,
    )

    assert exit_code == 1
    assert ingestion_calls == []


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("missing temporarily"),
        PermissionError("permission temporarily denied"),
        OSError("filesystem temporarily unavailable"),
    ],
)
def test_transient_os_errors_are_counted_but_not_persisted(
    tmp_path: Path, error: OSError
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()
    results: list[ingestor_module.ExecutionDiscoveryResult] = []

    _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: (_ for _ in ()).throw(error),
        stats=stats,
        discovery_results=results,
    )

    assert stats["skipped_transient"] == 1
    assert stats["transient_execution_ids"] == 1
    assert stats["skipped_incomplete"] == 0
    assert stats["skipped_invalid"] == 0
    assert results == []


def test_all_accepted_results_persist_before_limit_and_deferred_bypasses_next_validation(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_a = archive_root / "case_a"
    case_b = archive_root / "case_b"
    (case_a / "100.1-1").mkdir(parents=True)
    (case_b / "200.1-1").mkdir(parents=True)
    state = _fresh_state()
    persisted_batches: list[list[ingestor_module.ExecutionDiscoveryResult]] = []
    ingested_paths: list[str] = []
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: state,
    )

    def persist_results(
        *args: Any,
        results: list[ingestor_module.ExecutionDiscoveryResult],
        **kwargs: Any,
    ) -> IngestionRequestResponse:
        persisted_batches.append(results)
        return {"status_code": 201, "body": {}}

    def ingest_case(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        **kwargs: Any,
    ) -> IngestionRequestResponse:
        ingested_paths.append(archive_path)
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=1,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: {},
            post_request_fn=ingest_case,
            discovery_post_request_fn=persist_results,
        )
        == 0
    )
    first_results = persisted_batches[0]
    assert {(result.case_identity, result.outcome) for result in first_results} == {
        ("case_a", "accepted"),
        ("case_b", "accepted"),
    }
    assert len(ingested_paths) == 1

    state["discovery_results"] = {
        result.case_identity: [
            {
                "case_identity": result.case_identity,
                "execution_id": result.execution_id,
                "outcome": result.outcome,
            }
        ]
        for result in first_results
    }
    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: pytest.fail(
                "stored result must bypass validation"
            ),
            post_request_fn=ingest_case,
            discovery_post_request_fn=persist_results,
        )
        == 0
    )
    assert len(ingested_paths) == 2
    assert set(ingested_paths) == {str(case_a.resolve()), str(case_b.resolve())}
    assert len(persisted_batches) == 1


def test_stored_rejected_results_bypass_validation_and_candidacy(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    (case_dir / "101.1-1").mkdir(parents=True)

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: pytest.fail(
            "stored rejection must bypass validation"
        ),
        discovery_results_by_key={
            (str(case_dir.resolve()), "100.1-1"): "rejected_incomplete",
            (str(case_dir.resolve()), "101.1-1"): "rejected_invalid",
        },
    )

    assert grouped == {}


def test_rejected_only_and_mixed_cases_persist_every_immutable_result(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    rejected_case = archive_root / "case_a"
    mixed_case = archive_root / "case_b"
    (rejected_case / "100.1-1").mkdir(parents=True)
    (mixed_case / "200.1-1").mkdir(parents=True)
    (mixed_case / "201.1-1").mkdir(parents=True)
    persisted: list[ingestor_module.ExecutionDiscoveryResult] = []
    ingested: list[str] = []
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    def locator(path: str) -> object:
        if path.endswith("100.1-1"):
            raise IncompleteArchiveError([])
        if path.endswith("201.1-1"):
            raise ArchiveValidationError([])
        return {}

    def persist(*args: Any, results, **kwargs: Any) -> IngestionRequestResponse:
        persisted.extend(results)
        return {"status_code": 201, "body": {}}

    def ingest(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        ingested.append(args[2])
        return {"status_code": 201, "body": {}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=locator,
            post_request_fn=ingest,
            discovery_post_request_fn=persist,
        )
        == 0
    )
    assert sorted((result.execution_id, result.outcome) for result in persisted) == [
        ("100.1-1", "rejected_incomplete"),
        ("200.1-1", "accepted"),
        ("201.1-1", "rejected_invalid"),
    ]
    assert ingested == [str(mixed_case.resolve())]


def test_discovery_persistence_retries_transient_failure() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def persist(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        attempts.append(1)
        if len(attempts) == 1:
            raise IngestionRequestError("temporary", status_code=503, transient=True)
        return {"status_code": 201, "body": {}}

    ok = ingestor_module._persist_discovery_results_with_retries(
        [
            ingestor_module.ExecutionDiscoveryResult(
                case_identity="case_a",
                execution_id="100.1-1",
                outcome="accepted",
            )
        ],
        "http://backend/discovery-results",
        "token",
        "perlmutter",
        max_attempts=2,
        timeout_seconds=30,
        sleep_fn=sleeps.append,
        post_request_fn=persist,
    )

    assert ok is True
    assert len(attempts) == 2
    assert sleeps == [1]


def test_dry_run_never_persists_discovery_results(tmp_path: Path, monkeypatch) -> None:
    archive_root = tmp_path / "performance_archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: {},
            discovery_post_request_fn=lambda *args, **kwargs: pytest.fail(
                "dry run must not persist"
            ),
        )
        == 0
    )


def test_failed_ingestion_keeps_accepted_execution_unprocessed(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    state = _fresh_state()
    persisted: list[ingestor_module.ExecutionDiscoveryResult] = []
    monkeypatch.setattr(
        ingestor_module,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: state,
    )

    def persist(*args: Any, results, **kwargs: Any) -> IngestionRequestResponse:
        persisted.extend(results)
        return {"status_code": 201, "body": {}}

    def fail_ingestion(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("failed", status_code=400, transient=False)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    assert (
        _run_ingestor(
            config,
            metadata_locator=lambda *_: {},
            post_request_fn=fail_ingestion,
            discovery_post_request_fn=persist,
        )
        == 1
    )
    assert [(result.execution_id, result.outcome) for result in persisted] == [
        ("100.1-1", "accepted")
    ]
    assert state["cases"] == {}


def test_validate_execution_dir_compacts_incomplete_archive_errors(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()

    decision = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(
            IncompleteArchiveError(
                [
                    {
                        "code": "missing_required_file",
                        "file_spec": "env_run.xml..*",
                        "message": "missing env_run",
                    },
                    {
                        "code": "missing_required_file",
                        "file_spec": "README.case..*.gz",
                        "message": "missing readme",
                    },
                ]
            )
        ),
        stats=stats,
    )

    assert decision is not None
    assert decision.to_log_fields() == {
        "case": str(case_dir.resolve()),
        "decision": "rejected",
        "execution_id": "100.1-1",
        "reason": "incomplete",
        "error_count": 2,
        "error_codes": ["missing_required_file"],
        "missing_file_specs": ["README.case..*.gz", "env_run.xml..*"],
    }
    assert stats["skipped_incomplete"] == 1


def test_validate_execution_dir_compacts_archive_validation_errors(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()

    decision = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(
            ArchiveValidationError(
                [
                    {
                        "code": "multiple_matching_files",
                        "file_spec": "CaseStatus..*.gz",
                        "message": "too many files",
                    },
                    {
                        "code": "missing_required_file",
                        "file_spec": "env_run.xml..*",
                        "message": "missing env_run",
                    },
                ]
            )
        ),
        stats=stats,
    )

    assert decision is not None
    assert decision.to_log_fields() == {
        "case": str(case_dir.resolve()),
        "decision": "rejected",
        "execution_id": "100.1-1",
        "reason": "invalid",
        "error_count": 2,
        "error_codes": ["missing_required_file", "multiple_matching_files"],
        "missing_file_specs": ["env_run.xml..*"],
    }
    assert stats["skipped_invalid"] == 1


def test_run_ingestor_logs_rejected_only_case_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []
    archive_root = tmp_path / "archive"
    case_a = archive_root / "case_a"
    case_b = archive_root / "case_b"
    (case_a / "100.1-1").mkdir(parents=True)
    (case_a / "101.1-1").mkdir(parents=True)
    (case_b / "200.1-1").mkdir(parents=True)

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    incomplete_error = IncompleteArchiveError([])
    incomplete_error.args = ("missing",)
    invalid_error = ArchiveValidationError([])
    invalid_error.args = ("bad metadata",)

    def fake_locator(execution_dir: str) -> dict[str, str]:
        if execution_dir.endswith("100.1-1"):
            raise incomplete_error
        if execution_dir.endswith("101.1-1"):
            raise invalid_error
        return {}

    exit_code = _run_ingestor(config, metadata_locator=fake_locator)

    case_block_events = [
        (event, fields)
        for event, fields in logged_events
        if event
        in {
            "case_collection_begin",
            "execution_collection_decision",
            "case_collection_summary",
        }
    ]

    assert exit_code == 0
    assert case_block_events == [
        (
            "case_collection_begin",
            {
                "case": "case_a",
                "execution_count_total": 2,
                "execution_count_valid": 0,
                "execution_count_rejected_incomplete": 1,
                "execution_count_rejected_invalid": 1,
                "execution_count_transient": 0,
                "execution_count_existing": 0,
                "execution_count_new": 0,
                "execution_count_selected_new": 0,
                "execution_count_deferred": 0,
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_a",
                "decision": "rejected",
                "execution_id": "100.1-1",
                "reason": "incomplete",
                "detail": "missing",
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_a",
                "decision": "rejected",
                "execution_id": "101.1-1",
                "reason": "invalid",
                "detail": "bad metadata",
            },
        ),
        (
            "case_collection_summary",
            {
                "case": "case_a",
                "accepted": 0,
                "rejected_existing": 0,
                "rejected_incomplete": 1,
                "rejected_invalid": 1,
                "transient": 0,
                "deferred": 0,
            },
        ),
        (
            "case_collection_begin",
            {
                "case": "case_b",
                "execution_count_total": 1,
                "execution_count_valid": 1,
                "execution_count_rejected_incomplete": 0,
                "execution_count_rejected_invalid": 0,
                "execution_count_transient": 0,
                "execution_count_existing": 0,
                "execution_count_new": 1,
                "execution_count_selected_new": 1,
                "execution_count_deferred": 0,
            },
        ),
        (
            "execution_collection_decision",
            {
                "case": "case_b",
                "decision": "accepted",
                "execution_id": "200.1-1",
                "reason": "new_execution",
            },
        ),
        (
            "case_collection_summary",
            {
                "case": "case_b",
                "accepted": 1,
                "rejected_existing": 0,
                "rejected_incomplete": 0,
                "rejected_invalid": 0,
                "transient": 0,
                "deferred": 0,
            },
        ),
    ]
    assert not any(
        event in {"execution_skipped_incomplete", "execution_skipped_invalid"}
        for event, _ in logged_events
    )


def test_run_ingestor_groups_case_logs_without_interleaving(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    case_b = archive_root / "case_b"
    case_a = archive_root / "case_a"
    (case_b / "200.1-1").mkdir(parents=True)
    (case_b / "201.1-1").mkdir(parents=True)
    (case_a / "100.1-1").mkdir(parents=True)
    (case_a / "101.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    case_block_markers = [
        (event, fields["case"])
        for event, fields in logged_events
        if event in {"case_collection_begin", "case_collection_summary"}
    ]

    assert exit_code == 0
    assert case_block_markers == [
        ("case_collection_begin", "case_a"),
        ("case_collection_summary", "case_a"),
        ("case_collection_begin", "case_b"),
        ("case_collection_summary", "case_b"),
    ]


def test_log_startup_configuration_emits_structured_block(
    monkeypatch, tmp_path: Path
) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=tmp_path,
        machine_name="pm",
        dry_run=True,
        max_cases_per_run=5,
        max_attempts=2,
        request_timeout_seconds=60,
    )
    _log_startup_configuration(
        config,
        endpoint_url="http://backend:8000/api/v1/ingestions/from-path",
        state_endpoint_url="http://backend:8000/api/v1/ingestions/state",
    )

    assert logged_events == [
        ("startup_configuration_begin", {}),
        (
            "startup_configuration_api",
            {
                "api_base_url": "http://backend:8000",
                "endpoint_url": "http://backend:8000/api/v1/ingestions/from-path",
                "state_endpoint_url": "http://backend:8000/api/v1/ingestions/state",
            },
        ),
        (
            "startup_configuration_paths",
            {
                "scan_mode": "staging",
                "archive_root": str(tmp_path),
                "archive_year_start": None,
                "archive_year_end": None,
            },
        ),
        (
            "startup_configuration_runtime",
            {
                "machine_name": "pm",
                "dry_run": True,
                "max_cases_per_run": 5,
                "max_attempts": 2,
                "request_timeout_seconds": 60,
            },
        ),
        ("startup_configuration_auth", {"has_api_token": True}),
        ("startup_configuration_end", {}),
    ]


def test_log_event_uses_event_specific_field_order(monkeypatch) -> None:
    logged_messages: list[str] = []

    monkeypatch.setattr(
        ingestor_module.logger,
        "info",
        lambda message: logged_messages.append(message),
    )

    _log_event(
        "execution_collection_decision",
        {
            "reason": "incomplete",
            "detail": "missing",
            "decision": "rejected",
            "error_count": 2,
            "execution_id": "100.1-1",
            "case": "case_a",
            "zzz": "tail",
        },
    )

    assert logged_messages == [
        "event=execution_collection_decision "
        "case=case_a execution_id=100.1-1 decision=rejected "
        "reason=incomplete error_count=2 detail=missing zzz=tail"
    ]
