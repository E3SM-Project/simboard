"""Focused tests for archive discovery decisions and snapshot settlement."""

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import pytest

from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
)
from app.scripts.ingestion import archive_discovery as discovery_module
from app.scripts.ingestion import archive_ingestor_core as core_module
from app.scripts.ingestion.archive_ingestor_core import (
    ArchiveSnapshotScan,
    CaseCollectionLogData,
    CaseScanResult,
    ExecutionCollectionDecision,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestorConfig,
    _fresh_state,
    _record_successful_case,
)
from app.scripts.ingestion.archive_layout import (
    _build_case_path_filter,
    _build_walk_dir_filter,
)

_build_case_scan_results = discovery_module._build_case_scan_results
_build_ingestion_candidates = discovery_module._build_ingestion_candidates
_discover_case_executions = discovery_module._discover_case_executions
_validate_execution_dir = discovery_module._validate_execution_dir


@pytest.mark.parametrize(
    ("execution_id", "stored_outcome", "error", "expected_grouped", "expected"),
    [
        (
            "100.1-1",
            None,
            None,
            set(),
            {"rejected_existing_execution_ids": 1},
        ),
        (
            "101.1-1",
            "accepted",
            None,
            {"101.1-1"},
            {"execution_dirs_accepted": 1},
        ),
        (
            "102.1-1",
            "rejected_incomplete",
            None,
            set(),
            {"skipped_incomplete": 1, "rejected_incomplete_execution_ids": 1},
        ),
        (
            "103.1-1",
            "rejected_invalid",
            None,
            set(),
            {"skipped_invalid": 1, "rejected_invalid_execution_ids": 1},
        ),
        (
            "104.1-1",
            None,
            None,
            {"104.1-1"},
            {"execution_dirs_scanned": 1, "execution_dirs_accepted": 1},
        ),
        (
            "105.1-1",
            None,
            IncompleteArchiveError([]),
            set(),
            {
                "execution_dirs_scanned": 1,
                "skipped_incomplete": 1,
                "rejected_incomplete_execution_ids": 1,
            },
        ),
        (
            "106.1-1",
            None,
            ArchiveValidationError([]),
            set(),
            {
                "execution_dirs_scanned": 1,
                "skipped_invalid": 1,
                "rejected_invalid_execution_ids": 1,
            },
        ),
        (
            "107.1-1",
            None,
            PermissionError("temporary"),
            set(),
            {
                "execution_dirs_scanned": 1,
                "skipped_transient": 1,
                "transient_execution_ids": 1,
            },
        ),
    ],
)
def test_collect_case_execution_records_each_decision_source(
    tmp_path: Path,
    execution_id: str,
    stored_outcome: str | None,
    error: BaseException | None,
    expected_grouped: set[str],
    expected: dict[str, int],
) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    grouped: dict[str, set[str]] = {}
    logs: dict[str, CaseCollectionLogData] = {}
    stats = discovery_module._new_discovery_stats()
    results: list[ExecutionDiscoveryResult] = []
    processed = defaultdict(set)
    if execution_id == "100.1-1":
        processed[str(case_dir.resolve())].add(execution_id)

    def metadata_locator(_: str) -> object:
        if stored_outcome is not None:
            pytest.fail("stored discovery outcomes must bypass validation")
        if error is not None:
            raise error
        return {}

    discovery_module._collect_case_execution(
        grouped,
        case_dir,
        execution_id,
        metadata_locator=metadata_locator,
        stats=stats,
        case_collection_data=logs,
        processed_ids_by_key=processed,
        scan_mode="staging",
        staging_root_basename="performance_archive",
        discovery_results=results,
        discovery_results_by_key=(
            {}
            if stored_outcome is None
            else {(str(case_dir.resolve()), execution_id): stored_outcome}
        ),
    )

    assert grouped.get(str(case_dir.resolve()), set()) == expected_grouped
    assert stats == {key: expected.get(key, 0) for key in stats}

    expected_results = {
        "104.1-1": [(execution_id, "accepted")],
        "105.1-1": [(execution_id, "rejected_incomplete")],
        "106.1-1": [(execution_id, "rejected_invalid")],
    }.get(execution_id, [])
    assert [(result.execution_id, result.outcome) for result in results] == (
        expected_results
    )
    log_data = logs[str(case_dir.resolve())]
    assert log_data.execution_count_total == 1
    assert log_data.valid_execution_ids == expected_grouped
    expected_rejection_reason = {
        "100.1-1": "already_processed",
        "102.1-1": "incomplete",
        "103.1-1": "invalid",
        "105.1-1": "incomplete",
        "106.1-1": "invalid",
        "107.1-1": "transient",
    }.get(execution_id)
    assert [decision.reason for decision in log_data.rejected_decisions] == (
        [] if expected_rejection_reason is None else [expected_rejection_reason]
    )


def test_collection_outcomes_preserve_order_fields_and_limit_counters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_a = str((tmp_path / "case-a").resolve())
    case_b = str((tmp_path / "case-b").resolve())
    collection_data = {
        case_b: CaseCollectionLogData(
            case_path=case_b,
            execution_count_total=1,
            valid_execution_ids={"200.1-1"},
        ),
        case_a: CaseCollectionLogData(
            case_path=case_a,
            execution_count_total=3,
            valid_execution_ids={"100.1-1", "101.1-1"},
            rejected_decisions=[
                ExecutionCollectionDecision(
                    case_path=case_a,
                    execution_id="099.1-1",
                    decision="rejected",
                    reason="invalid",
                )
            ],
        ),
    }
    state = {"cases": {case_a: {"processed_execution_ids": ["100.1-1"]}}}
    candidates = [
        IngestionCandidate(
            case_path=case_a,
            execution_ids=["100.1-1", "101.1-1"],
            new_execution_ids=["101.1-1"],
            fingerprint="ignored",
        )
    ]
    stats = discovery_module._new_discovery_stats()
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        discovery_module,
        "_log_event",
        lambda event, fields=None: events.append((event, fields or {})),
    )

    discovery_module._log_execution_collection_outcomes(
        collection_data,
        state,
        candidates,
        stats,
        archive_root=tmp_path,
    )

    assert [event for event, _ in events] == [
        "case_collection_begin",
        "execution_collection_decision",
        "execution_collection_decision",
        "execution_collection_decision",
        "case_collection_summary",
        "case_collection_begin",
        "execution_collection_decision",
        "case_collection_summary",
    ]
    assert list(events[0][1]) == [
        "case",
        "execution_count_total",
        "execution_count_valid",
        "execution_count_rejected_incomplete",
        "execution_count_rejected_invalid",
        "execution_count_transient",
        "execution_count_existing",
        "execution_count_new",
        "execution_count_selected_new",
        "execution_count_deferred",
    ]
    assert events[0][1] == {
        "case": "case-a",
        "execution_count_total": 3,
        "execution_count_valid": 2,
        "execution_count_rejected_incomplete": 0,
        "execution_count_rejected_invalid": 1,
        "execution_count_transient": 0,
        "execution_count_existing": 1,
        "execution_count_new": 1,
        "execution_count_selected_new": 1,
        "execution_count_deferred": 0,
    }
    assert events[-1] == (
        "case_collection_summary",
        {
            "case": "case-b",
            "accepted": 0,
            "rejected_existing": 0,
            "rejected_incomplete": 0,
            "rejected_invalid": 0,
            "transient": 0,
            "deferred": 1,
        },
    )
    assert stats["accepted_execution_ids"] == 1
    assert stats["rejected_existing_execution_ids"] == 1
    assert stats["rejected_invalid_execution_ids"] == 0
    assert stats["deferred_execution_ids"] == 1


@pytest.mark.parametrize(
    ("traversal_complete", "outcome", "processed", "expected_settled"),
    [
        pytest.param(True, None, True, True, id="processed"),
        pytest.param(
            True,
            "rejected_incomplete",
            False,
            True,
            id="immutable-incomplete",
        ),
        pytest.param(True, "rejected_invalid", False, True, id="immutable-invalid"),
        pytest.param(True, "accepted", False, False, id="failed-ingestion"),
        pytest.param(True, None, False, False, id="transient-discovery"),
        pytest.param(True, None, False, False, id="deferred-candidate"),
        pytest.param(
            False,
            "rejected_invalid",
            False,
            False,
            id="incomplete-traversal",
        ),
    ],
)
def test_snapshot_settlement_requires_permanent_resolution(
    traversal_complete: bool,
    outcome: Literal["accepted", "rejected_incomplete", "rejected_invalid"] | None,
    processed: bool,
    expected_settled: bool,
) -> None:
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    execution_id = "100.1-1"
    snapshot_scan = ArchiveSnapshotScan(
        archive_name="OLD_PERF",
        eligible_keys={snapshot_key},
        references_by_key={snapshot_key: {("case-a", execution_id)}},
        traversal_complete=traversal_complete,
    )
    state = _fresh_state()
    if processed:
        state["cases"] = {
            "case-a": {"processed_execution_ids": [execution_id]},
        }
    results = (
        []
        if outcome is None
        else [
            ExecutionDiscoveryResult(
                case_identity="case-a",
                execution_id=execution_id,
                outcome=outcome,
            )
        ]
    )

    settled = discovery_module._settled_archive_snapshot_keys(
        snapshot_scan,
        state,
        results,
    )

    assert (snapshot_key in settled) is expected_settled


def test_empty_selected_snapshot_settles_vacuously() -> None:
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    snapshot_scan = ArchiveSnapshotScan(
        archive_name="OLD_PERF",
        eligible_keys={snapshot_key},
    )

    assert discovery_module._settled_archive_snapshot_keys(
        snapshot_scan,
        _fresh_state(),
        [],
    ) == {snapshot_key}


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

    stats = discovery_module._new_discovery_stats()

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
    assert stats["skipped_transient"] == 1
    assert stats["transient_execution_ids"] == 1


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

    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)

    case_collection_data: dict[str, discovery_module.CaseCollectionLogData] = {}
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

    monkeypatch.setattr(discovery_module, "_log_event", fake_log_event)
    monkeypatch.setattr(discovery_module, "DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES", 2)

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
    discovery_results: list[core_module.ExecutionDiscoveryResult] = []
    stats = discovery_module._new_discovery_stats()
    processed_ids_by_key = discovery_module._build_processed_ids_by_key(
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
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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
    assert stats["skipped_transient"] == 1
    assert stats["transient_execution_ids"] == 1


def test_validate_execution_dir_counts_archive_validation_error_with_stats(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = discovery_module._new_discovery_stats()

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


def test_discovery_results_capture_typed_outcomes_but_not_transient_errors(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    case_dir = archive_root / "case_a"
    for execution_id in ("100.1-1", "101.1-1", "102.1-1", "103.1-1"):
        (case_dir / execution_id).mkdir(parents=True)
    results: list[core_module.ExecutionDiscoveryResult] = []

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
    stats = discovery_module._new_discovery_stats()
    results: list[core_module.ExecutionDiscoveryResult] = []

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


def test_validate_execution_dir_compacts_incomplete_archive_errors(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = discovery_module._new_discovery_stats()

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
    stats = discovery_module._new_discovery_stats()

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


def test_archive_scan_skips_database_completed_snapshots(tmp_path: Path) -> None:
    archive_root = tmp_path / "OLD_PERF"
    first_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    second_key = "2025-01/performance_archive_2025_01_02_00_00_00"
    for key, execution_id in ((first_key, "100.1-1"), (second_key, "101.1-1")):
        (archive_root / key / "COMPLETED" / "case-a" / execution_id).mkdir(parents=True)
    visited: list[str] = []
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="pm",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
    )

    results = discovery_module._scan_archive(
        config,
        _fresh_state(),
        metadata_locator=lambda path: visited.append(path),
        completed_snapshot_keys={first_key},
    )

    assert len(results) == 5
    assert visited == [
        str(archive_root / second_key / "COMPLETED" / "case-a" / "101.1-1")
    ]
    assert results[4].eligible_keys == {first_key, second_key}
    assert results[4].completed_keys == {first_key}


def test_archive_scan_falls_back_when_month_has_no_snapshot_directory(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    execution_dir = archive_root / "2025-01" / "user-a" / "case-a" / "100.1-1"
    execution_dir.mkdir(parents=True)
    visited: list[str] = []
    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="chrysalis",
        dry_run=True,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2025-01",
    )

    results = discovery_module._scan_archive(
        config,
        _fresh_state(),
        metadata_locator=lambda path: visited.append(path),
    )

    assert visited == [str(execution_dir)]
    assert [result.case_path for result in results[0]] == [
        str(execution_dir.parent.resolve())
    ]
    assert results[4].eligible_keys == set()


def test_snapshot_settlement_requires_ingested_or_immutable_rejected() -> None:
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    snapshot_scan = discovery_module.ArchiveSnapshotScan(
        archive_name="OLD_PERF",
        eligible_keys={snapshot_key},
        references_by_key={
            snapshot_key: {
                ("case-a", "100.1-1"),
                ("case-a", "101.1-1"),
                ("case-a", "102.1-1"),
            }
        },
    )
    state = _fresh_state()
    state["cases"] = {
        "case-a": {"processed_execution_ids": ["100.1-1"]},
    }
    results = [
        core_module.ExecutionDiscoveryResult(
            case_identity="case-a",
            execution_id="101.1-1",
            outcome="rejected_invalid",
        ),
        core_module.ExecutionDiscoveryResult(
            case_identity="case-a",
            execution_id="102.1-1",
            outcome="accepted",
        ),
    ]

    assert (
        discovery_module._settled_archive_snapshot_keys(snapshot_scan, state, results)
        == set()
    )

    state["cases"]["case-a"]["processed_execution_ids"].append("102.1-1")
    assert discovery_module._settled_archive_snapshot_keys(
        snapshot_scan, state, results
    ) == {snapshot_key}


@pytest.mark.parametrize(
    "results",
    [
        [
            core_module.ExecutionDiscoveryResult(
                case_identity="case-a",
                execution_id="100.1-1",
                outcome="accepted",
            ),
            core_module.ExecutionDiscoveryResult(
                case_identity="case-a",
                execution_id="100.1-1",
                outcome="rejected_invalid",
            ),
        ],
        [
            core_module.ExecutionDiscoveryResult(
                case_identity="case-a",
                execution_id="100.1-1",
                outcome="rejected_invalid",
            ),
            core_module.ExecutionDiscoveryResult(
                case_identity="case-a",
                execution_id="100.1-1",
                outcome="accepted",
            ),
        ],
    ],
)
def test_snapshot_settlement_uses_order_independent_discovery_precedence(
    results: list[core_module.ExecutionDiscoveryResult],
) -> None:
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    snapshot_scan = discovery_module.ArchiveSnapshotScan(
        archive_name="OLD_PERF",
        eligible_keys={snapshot_key},
        references_by_key={snapshot_key: {("case-a", "100.1-1")}},
    )

    assert (
        discovery_module._settled_archive_snapshot_keys(
            snapshot_scan,
            _fresh_state(),
            results,
        )
        == set()
    )
