"""Tests for shared archive ingestion workflow phases."""

from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from app.scripts.ingestion.archive_discovery import _new_discovery_stats
from app.scripts.ingestion.archive_ingestor_core import (
    ArchiveSnapshotScan,
    ExecutionDiscoveryResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    IngestorRunReport,
    _fresh_state,
)
from app.scripts.ingestion.archive_workflow import (
    _finalize_archive_checkpoints,
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


def _candidate(case_path: Path) -> IngestionCandidate:
    return IngestionCandidate(
        case_path=str(case_path),
        execution_ids=["100.1-1"],
        new_execution_ids=["100.1-1"],
        fingerprint="fingerprint",
    )


def test_validate_run_preconditions_logs_failures(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    def log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        events.append((event, fields or {}))

    missing_root = tmp_path / "missing"
    assert not _validate_run_preconditions(
        _config(missing_root), log_event_fn=log_event
    )
    assert events == [("archive_root_missing", {"archive_root": str(missing_root)})]

    config = replace(_config(tmp_path, dry_run=True), api_token="")
    assert not _validate_run_preconditions(config, log_event_fn=log_event)
    assert _validate_run_preconditions(
        replace(config, dry_run_use_remote_state=False), log_event_fn=log_event
    )
    assert not _validate_run_preconditions(
        replace(config, dry_run=False), log_event_fn=log_event
    )
    assert events[-1] == (
        "configuration_error",
        {"error": "SIMBOARD_API_TOKEN is required"},
    )


def test_startup_configuration_has_no_derived_urls_or_block_markers(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    config = _config(tmp_path, dry_run=True)
    _log_startup_configuration(
        config,
        log_event_fn=lambda event, fields=None: events.append((event, fields or {})),
    )
    assert events == [
        ("startup_configuration_api", {"api_base_url": config.api_base_url}),
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
                "machine_name": "perlmutter",
                "dry_run": True,
                "dry_run_use_remote_state": True,
                "max_cases_per_run": None,
                "max_attempts": 1,
                "request_timeout_seconds": 30,
            },
        ),
        ("startup_configuration_auth", {"has_api_token": True}),
    ]


def test_scan_completed_keeps_selection_and_validation_diagnostics(
    tmp_path: Path,
) -> None:
    stats = _new_discovery_stats()
    stats.update(
        execution_dirs_scanned=11,
        execution_dirs_accepted=10,
        skipped_incomplete=1,
        skipped_invalid=2,
        skipped_transient=3,
        accepted_execution_ids=4,
    )
    events: list[tuple[str, dict[str, Any]]] = []
    _log_scan_completed(
        [_candidate(tmp_path / "case")],
        2,
        stats,
        log_event_fn=lambda event, fields=None: events.append((event, fields or {})),
    )
    assert events == [
        (
            "scan_completed",
            {
                "submission_qualified_cases": 2,
                "selected_submission_cases": 1,
                "execution_dirs_scanned": 11,
                "execution_dirs_accepted": 10,
                "skipped_incomplete": 1,
                "skipped_invalid": 2,
                "skipped_transient": 3,
            },
        )
    ]


def test_ingestion_failure_preserves_state_and_records_completion(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    state = _fresh_state()
    report = IngestorRunReport()

    def post(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        raise IngestionRequestError("boom", status_code=503, transient=False)

    assert (
        _handle_ingest_run(
            [_candidate(tmp_path / "case")],
            _config(tmp_path),
            "http://backend:8000/api/v1/ingestions/from-path",
            state,
            sleep_fn=lambda *_: None,
            post_request_fn=post,
            log_event_fn=lambda event, fields=None: events.append(
                (event, fields or {})
            ),
            run_report=report,
        )
        == 1
    )
    assert events == [
        (
            "case_ingestion_failed",
            {
                "case_path": str(tmp_path / "case"),
                "attempts": 1,
                "status_code": 503,
                "error": "boom",
            },
        ),
        ("run_completed", {}),
    ]
    assert state["cases"] == {}
    assert report.ingestion_failure_count == 1
    assert report.ingestion_success_count == 0


@pytest.mark.parametrize("interactive", [True, False])
def test_ingest_case_progress_only_on_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interactive: bool
) -> None:
    class ProgressStream(StringIO):
        def isatty(self) -> bool:
            return interactive

    stream = ProgressStream()
    monkeypatch.setattr("sys.stderr", stream)
    cases = [_candidate(tmp_path / "case_a"), _candidate(tmp_path / "case_b")]
    logged_events: list[str] = []

    def post_request(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        if args[2] == cases[1].case_path:
            raise IngestionRequestError("failed", status_code=400, transient=False)
        return {"status_code": 201, "body": {"created_count": 1}}

    exit_code = _handle_ingest_run(
        cases,
        _config(tmp_path),
        "http://backend:8000/api/v1/ingestions/from-path",
        _fresh_state(),
        sleep_fn=lambda *_: None,
        post_request_fn=post_request,
        log_event_fn=lambda event, fields=None: logged_events.append(event),
    )

    assert exit_code == 1
    assert "case_ingested" in logged_events
    assert "case_ingestion_failed" in logged_events
    assert ("2/2" in stream.getvalue()) is interactive
    if not interactive:
        assert stream.getvalue() == ""


def test_success_separates_response_details_from_outcome(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "case")
    events: list[tuple[str, dict[str, Any]]] = []
    state = _fresh_state()
    report = IngestorRunReport()
    requests: list[dict[str, Any]] = []

    def post(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        requests.append(kwargs)
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    assert (
        _handle_ingest_run(
            [candidate],
            _config(tmp_path),
            "http://backend:8000/ingest",
            state,
            sleep_fn=lambda *_: None,
            post_request_fn=post,
            log_event_fn=lambda event, fields=None: events.append(
                (event, fields or {})
            ),
            run_report=report,
        )
        == 0
    )
    assert events == [
        (
            "case_submission_details",
            {
                "case_path": candidate.case_path,
                "attempts": 1,
                "created_count": 1,
                "duplicate_count": 0,
                "error_count": 0,
            },
        ),
        ("case_ingested", {"case_path": candidate.case_path}),
        ("run_completed", {}),
    ]
    assert requests[0]["processed_execution_ids"] == candidate.new_execution_ids
    assert state["cases"][candidate.case_path]["processed_execution_ids"] == ["100.1-1"]
    assert report.ingestion_success_count == 1
    assert report.ingestion_failure_count == 0


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
    captured: list[str] = []

    def persist(
        *args: Any, snapshot_keys: list[str], **kwargs: Any
    ) -> IngestionRequestResponse:
        captured.extend(snapshot_keys)
        return {"status_code": 201, "body": {}}

    assert _finalize_archive_checkpoints(
        snapshot_scan,
        _fresh_state(),
        [ExecutionDiscoveryResult("case_a", "100.1-1", "rejected_invalid")],
        "http://backend:8000/api/v1/ingestions/archive-checkpoints",
        replace(_config(tmp_path), scan_mode="archive"),
        lambda *_: None,
        persist,
    )
    assert captured == [snapshot_key]
