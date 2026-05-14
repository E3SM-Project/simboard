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
from app.scripts.ingestion import nersc_archive_ingestor as ingestor_module
from app.scripts.ingestion.nersc_archive_ingestor import (
    CaseScanResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestionRequestResponse,
    IngestorConfig,
    _build_case_scan_results,
    _build_config_from_env,
    _build_ingestion_candidates,
    _case_state_processed_ids,
    _discover_case_executions,
    _fresh_state,
    _ingest_case_with_retries,
    _is_transient_status,
    _load_state,
    _log_execution_skip_detail,
    _log_startup_configuration,
    _log_summary_table,
    _normalized_api_base_url,
    _parse_bool,
    _parse_optional_int,
    _post_ingestion_request,
    _record_successful_case,
    _render_log_value,
    _run_ingestor,
    _save_state,
    _validate_execution_dir,
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
    assert stats["skipped_invalid"] == 1


def test_discover_case_executions_logs_suppressed_skips(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_root = tmp_path / "archive"
    for index in range(ingestor_module.MAX_SKIP_DETAIL_LOGS + 2):
        (archive_root / "case_a" / f"{100 + index}.1-1").mkdir(parents=True)

    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    grouped = _discover_case_executions(
        archive_root,
        metadata_locator=lambda *_: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )

    assert grouped == {}
    suppression = [
        fields
        for event, fields in logged_events
        if event == "execution_skip_logs_suppressed"
    ]
    assert suppression == [
        {
            "suppressed_count": 2,
            "detail_log_limit": ingestor_module.MAX_SKIP_DETAIL_LOGS,
        }
    ]


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


def test_validate_execution_dir_counts_incomplete_with_stats(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()
    skip_log_state = {"logged": 0, "suppressed": 0}

    valid = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(FileNotFoundError("missing")),
        stats=stats,
        skip_log_state=skip_log_state,
    )

    assert valid is False
    assert stats["skipped_incomplete"] == 1


def test_validate_execution_dir_counts_value_error_with_stats(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)
    stats = ingestor_module._new_discovery_stats()
    skip_log_state = {"logged": 0, "suppressed": 0}

    valid = _validate_execution_dir(
        case_dir,
        "100.1-1",
        metadata_locator=lambda *_: (_ for _ in ()).throw(ValueError("invalid")),
        stats=stats,
        skip_log_state=skip_log_state,
    )

    assert valid is False
    assert stats["skipped_invalid"] == 1


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


def test_run_ingestor_persists_state_and_builds_expected_payload(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "performance_archive"
    case_dir = archive_root / "case_a"
    (case_dir / "100.1-1").mkdir(parents=True)

    state_path = tmp_path / "state.json"
    captured_calls: list[dict[str, str]] = []

    def fake_post_request(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured_calls.append(
            {
                "endpoint_url": endpoint_url,
                "api_token": api_token,
                "archive_path": archive_path,
                "machine_name": machine_name,
                "timeout_seconds": str(timeout_seconds),
            }
        )
        return {
            "status_code": 201,
            "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
        }

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token-123",
        archive_root=archive_root,
        machine_name="perlmutter",
        state_path=state_path,
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
        "timeout_seconds": "30",
    }

    reloaded_state = _fresh_state()
    reloaded_state.update(
        __import__("json").loads(state_path.read_text(encoding="utf-8"))
    )
    assert str(case_dir.resolve()) in reloaded_state["cases"]


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
        state_path=tmp_path / "state.json",
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


def test_run_ingestor_dry_run_without_token_succeeds(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    (archive_root / "case_a" / "100.1-1").mkdir(parents=True)
    call_count = 0

    def fake_post_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {"status_code": 201, "body": {"created_count": 1, "errors": []}}

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="",
        archive_root=archive_root,
        machine_name="perlmutter",
        state_path=tmp_path / "state.json",
        dry_run=True,
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
    assert call_count == 0


def test_run_ingestor_non_dry_run_without_token_returns_config_error(
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
        state_path=tmp_path / "state.json",
        dry_run=False,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
    )

    exit_code = _run_ingestor(config, metadata_locator=lambda *_: {})

    assert exit_code == 1
    assert any(event == "configuration_error" for event, _ in logged_events)
    assert not any(event == "scan_completed" for event, _ in logged_events)


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
        state_path=tmp_path / "state.json",
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
        api_token="",
        archive_root=archive_root,
        machine_name="perlmutter",
        state_path=tmp_path / "state.json",
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
    assert exit_code == 0
    assert len(suppression_events) == 1
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
        api_token="",
        archive_root=dry_archive,
        machine_name="perlmutter",
        state_path=tmp_path / "dry_state.json",
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
        state_path=tmp_path / "ingest_state.json",
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

    for payload in (dry_run_completed, run_completed):
        assert isinstance(payload["execution_dirs_scanned"], int)
        assert isinstance(payload["execution_dirs_accepted"], int)
        assert isinstance(payload["skipped_incomplete"], int)
        assert isinstance(payload["skipped_invalid"], int)


def test_build_config_from_env_parses_valid_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "http://example")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("PERF_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("MACHINE_NAME", "pm")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("MAX_CASES_PER_RUN", "5")
    monkeypatch.setenv("MAX_ATTEMPTS", "4")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "90")

    config = _build_config_from_env()

    assert config.api_base_url == "http://example"
    assert config.api_token == "token"
    assert config.archive_root == (tmp_path / "archive").resolve()
    assert config.machine_name == "pm"
    assert config.state_path == (tmp_path / "state.json").resolve()
    assert config.dry_run is True
    assert config.max_cases_per_run == 5
    assert config.max_attempts == 4
    assert config.request_timeout_seconds == 90


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
    ],
)
def test_build_config_from_env_rejects_invalid_positive_values(
    monkeypatch,
    env_name: str,
    env_value: str,
    message: str,
) -> None:
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
        state_path=tmp_path / "state.json",
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


def test_generic_hpc_module_main_guard_delegates_to_ingestor(monkeypatch) -> None:
    script_path = (
        Path(__file__).resolve().parents[3]
        / "app/scripts/ingestion/hpc_archive_ingestor.py"
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
    captured: list[tuple[str, str, str, str, int]] = []

    def fake_post(
        endpoint_url: str,
        api_token: str,
        archive_path: str,
        machine_name: str,
        *,
        timeout_seconds: int,
    ) -> IngestionRequestResponse:
        captured.append(
            (endpoint_url, api_token, archive_path, machine_name, timeout_seconds)
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
        timeout_seconds=12,
    )

    assert response == {"status_code": 201, "body": {"created_count": 1}}
    assert captured_request[0].headers["Authorization"] == "Bearer token"


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
            timeout_seconds=12,
        )


def test_is_transient_status() -> None:
    assert _is_transient_status(503) is True
    assert _is_transient_status(400) is False


def test_load_state_handles_invalid_json_and_logs(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{invalid", encoding="utf-8")
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    state = _load_state(state_path)

    assert state["version"] == ingestor_module.STATE_VERSION
    assert logged_events[0][0] == "state_load_failed"


def test_load_state_handles_non_dict_root_and_non_dict_cases(tmp_path: Path) -> None:
    non_dict_path = tmp_path / "not_dict.json"
    non_dict_path.write_text("[]", encoding="utf-8")
    assert _load_state(non_dict_path)["cases"] == {}

    bad_cases_path = tmp_path / "bad_cases.json"
    bad_cases_path.write_text(
        json.dumps(
            {"version": 9, "cases": [], "updated_at": "2024-01-01T00:00:00+00:00"}
        ),
        encoding="utf-8",
    )
    loaded = _load_state(bad_cases_path)
    assert loaded["cases"] == {}
    assert loaded["version"] == 9


def test_save_state_round_trips(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "state.json"
    state = {"version": 1, "cases": {}}

    _save_state(state_path, state)

    assert state_path.exists()
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["version"] == 1
    assert "updated_at" in saved


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


def test_log_execution_skip_detail_suppresses_after_limit(monkeypatch) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)
    skip_log_state = {"logged": ingestor_module.MAX_SKIP_DETAIL_LOGS, "suppressed": 0}

    _log_execution_skip_detail(
        "execution_skipped_incomplete",
        "/archive/case_a",
        "100.1-1",
        "missing",
        skip_log_state,
    )

    assert logged_events == []
    assert skip_log_state["suppressed"] == 1


def test_log_summary_table_and_startup_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event: str, fields: dict[str, Any] | None = None) -> None:
        logged_events.append((event, {} if fields is None else fields))

    monkeypatch.setattr(ingestor_module, "_log_event", fake_log_event)

    _log_summary_table("summary", [("a", 1), ("b", "two words")])

    config = IngestorConfig(
        api_base_url="http://backend:8000",
        api_token="token",
        archive_root=tmp_path,
        machine_name="pm",
        state_path=tmp_path / "state.json",
        dry_run=True,
        max_cases_per_run=5,
        max_attempts=2,
        request_timeout_seconds=60,
    )
    _log_startup_configuration(
        config, endpoint_url="http://backend:8000/api/v1/ingestions/from-path"
    )

    assert logged_events[0][0] == "summary_table"
    assert logged_events[1][0] == "startup_configuration_begin"
    assert logged_events[2][0] == "summary_table"
    assert logged_events[3][0] == "startup_configuration_end"
