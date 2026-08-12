"""Tests for shared archive ingestion workflow phases."""

from dataclasses import replace
from pathlib import Path
from typing import Any

from app.scripts.ingestion.archive_discovery import _new_discovery_stats
from app.scripts.ingestion.archive_ingestor_core import (
    MAX_DRY_RUN_CANDIDATE_LOGS,
    ArchiveSnapshotScan,
    CaseScanResult,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _fresh_state,
)
from app.scripts.ingestion.archive_workflow import (
    _finalize_archive_checkpoints,
    _handle_dry_run,
    _handle_ingest_run,
    _log_scan_completed,
    _log_startup_configuration,
    _persist_discovery_results,
    _validate_run_preconditions,
)


def _config(archive_root: Path, *, dry_run: bool = False) -> IngestorConfig:
    return IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=archive_root,
        machine_name="perlmutter",
        dry_run=dry_run,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )


def _candidate(case_path: Path, execution_id: str = "100.1-1") -> IngestionCandidate:
    return IngestionCandidate(
        case_path=str(case_path),
        execution_ids=[execution_id],
        new_execution_ids=[execution_id],
        fingerprint="fingerprint",
    )


def _scan_result(case_path: Path, execution_id: str = "100.1-1") -> CaseScanResult:
    return CaseScanResult(
        case_path=str(case_path),
        execution_ids=[execution_id],
        fingerprint="fingerprint",
    )


def test_validate_run_preconditions_logs_failures(tmp_path: Path) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    missing_root = tmp_path / "missing"
    assert not _validate_run_preconditions(
        _config(missing_root),
        log_event_fn=log_event,
    )
    assert logged_events == [
        ("archive_root_missing", {"archive_root": str(missing_root)})
    ]

    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    default_dry_run_config = replace(_config(archive_root, dry_run=True), api_token="")
    assert not _validate_run_preconditions(
        default_dry_run_config, log_event_fn=log_event
    )

    dry_run_config = replace(default_dry_run_config, dry_run_use_remote_state=False)
    assert _validate_run_preconditions(dry_run_config, log_event_fn=log_event)

    ingest_config = replace(_config(archive_root), api_token="")
    assert not _validate_run_preconditions(ingest_config, log_event_fn=log_event)
    assert logged_events[-1] == (
        "configuration_error",
        {"error": "SIMBOARD_API_TOKEN is required"},
    )


def test_log_startup_configuration_emits_structured_block(tmp_path: Path) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

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
        log_event_fn=fake_log_event,
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
                "dry_run_use_remote_state": True,
                "max_cases_per_run": 5,
                "max_attempts": 2,
                "request_timeout_seconds": 60,
            },
        ),
        ("startup_configuration_auth", {"has_api_token": True}),
        ("startup_configuration_end", {}),
    ]


def test_log_scan_completed_includes_discovery_summary_fields(tmp_path: Path) -> None:
    stats = _new_discovery_stats()
    stats["execution_dirs_scanned"] = 11
    stats["execution_dirs_accepted"] = 10
    stats["skipped_incomplete"] = 1
    stats["skipped_invalid"] = 2
    stats["skipped_transient"] = 3
    stats["accepted_execution_ids"] = 4
    stats["rejected_existing_execution_ids"] = 5
    stats["rejected_incomplete_execution_ids"] = 6
    stats["rejected_invalid_execution_ids"] = 7
    stats["transient_execution_ids"] = 8
    stats["deferred_execution_ids"] = 9
    case_path = tmp_path / "case_a"
    logged_events: list[tuple[str, dict[str, Any]]] = []

    _log_scan_completed(
        _config(tmp_path),
        [_scan_result(case_path)],
        [_candidate(case_path)],
        2,
        stats,
        log_event_fn=lambda event, fields=None: logged_events.append(
            (event, {} if fields is None else fields)
        ),
    )

    assert logged_events == [
        (
            "scan_completed",
            {
                "scan_mode": "staging",
                "archive_root": str(tmp_path),
                "discovered_cases": 1,
                "submission_qualified_cases": 2,
                "selected_submission_cases": 1,
                **stats,
            },
        )
    ]


def test_dry_run_candidate_suppression_event_emitted_once(tmp_path: Path) -> None:
    candidates = [
        _candidate(tmp_path / f"case_{index:03d}")
        for index in range(MAX_DRY_RUN_CANDIDATE_LOGS + 5)
    ]
    logged_events: list[tuple[str, dict[str, Any]]] = []

    exit_code = _handle_dry_run(
        candidates,
        [],
        len(candidates),
        _new_discovery_stats(),
        archive_root=tmp_path,
        log_event_fn=lambda event, fields=None: logged_events.append(
            (event, {} if fields is None else fields)
        ),
    )

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
    assert suppression_events[0]["detail_log_limit"] == MAX_DRY_RUN_CANDIDATE_LOGS


def test_handle_ingest_run_returns_failure_when_case_ingestion_fails(
    tmp_path: Path,
) -> None:
    case_path = tmp_path / "case_a"
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("boom", status_code=503, transient=False)

    exit_code = _handle_ingest_run(
        [_candidate(case_path)],
        [_scan_result(case_path)],
        _config(tmp_path),
        "http://backend:8000/api/v1/ingestions/from-path",
        _fresh_state(),
        1,
        _new_discovery_stats(),
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
        log_event_fn=lambda event, fields=None: logged_events.append(
            (event, {} if fields is None else fields)
        ),
    )

    assert exit_code == 1
    assert any(event == "case_ingestion_failed" for event, _ in logged_events)


def test_completion_events_include_summary_counters(tmp_path: Path) -> None:
    dry_case_path = tmp_path / "case_dry"
    ingest_case_path = tmp_path / "case_ingest"
    stats = _new_discovery_stats()
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    _handle_dry_run(
        [_candidate(dry_case_path)],
        [_scan_result(dry_case_path)],
        1,
        stats,
        archive_root=tmp_path,
        log_event_fn=fake_log_event,
    )

    def fake_ingest_post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    _handle_ingest_run(
        [_candidate(ingest_case_path)],
        [_scan_result(ingest_case_path)],
        _config(tmp_path),
        "http://backend:8000/api/v1/ingestions/from-path",
        _fresh_state(),
        1,
        stats,
        sleep_fn=lambda *_: None,
        post_request_fn=fake_ingest_post_request,
        log_event_fn=fake_log_event,
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


def test_persist_discovery_results_passes_explicit_run_configuration(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    results = [ExecutionDiscoveryResult("case_a", "100.1-1", "accepted")]

    def persist(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status_code": 201, "body": {}}

    assert _persist_discovery_results(
        results,
        "http://backend:8000/api/v1/ingestions/discovery-results",
        _config(tmp_path),
        lambda *_: None,
        persist,
    )
    assert captured["args"] == (
        "http://backend:8000/api/v1/ingestions/discovery-results",
        "token",
        "perlmutter",
    )
    assert captured["kwargs"]["results"] == results
    assert captured["kwargs"]["timeout_seconds"] == 30


def test_finalize_archive_checkpoints_only_persists_settled_archive_keys(
    tmp_path: Path,
) -> None:
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    snapshot_scan = ArchiveSnapshotScan(
        archive_name="OLD_PERF",
        eligible_keys={snapshot_key},
        references_by_key={snapshot_key: {("case_a", "100.1-1")}},
    )
    config = replace(_config(tmp_path), scan_mode="archive")
    captured_snapshot_keys: list[str] = []

    def persist(
        *args: Any, snapshot_keys: list[str], **kwargs: Any
    ) -> IngestionRequestResponse:
        captured_snapshot_keys.extend(snapshot_keys)
        return {"status_code": 201, "body": {}}

    assert _finalize_archive_checkpoints(
        snapshot_scan,
        _fresh_state(),
        [ExecutionDiscoveryResult("case_a", "100.1-1", "rejected_invalid")],
        "http://backend:8000/api/v1/ingestions/archive-checkpoints",
        config,
        lambda *_: None,
        persist,
    )
    assert captured_snapshot_keys == [snapshot_key]
