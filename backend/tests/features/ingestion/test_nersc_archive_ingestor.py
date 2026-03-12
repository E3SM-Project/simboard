"""Tests for the NERSC archive ingestion runner script."""

from pathlib import Path

from app.scripts.ingestion.nersc_archive_ingestor import (
    CaseScanResult,
    IngestionCandidate,
    IngestionRequestError,
    IngestorConfig,
    _fresh_state,
    _record_successful_case,
    build_case_scan_results,
    build_ingestion_candidates,
    discover_case_executions,
    ingest_case_with_retries,
    run_ingestor,
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

    grouped = discover_case_executions(archive_root, metadata_locator=fake_locator)

    assert list(grouped.values()) == [["100.1-1"]]


def test_build_ingestion_candidates_is_idempotent() -> None:
    scan_results = [
        CaseScanResult(
            case_path="/performance_archive/case_a",
            execution_ids=["100.1-1"],
            fingerprint="fp-1",
        )
    ]
    state = _fresh_state()

    first_candidates = build_ingestion_candidates(
        scan_results,
        state,
        max_cases_per_run=None,
    )
    assert len(first_candidates) == 1
    assert first_candidates[0].new_execution_ids == ["100.1-1"]

    _record_successful_case(state, first_candidates[0])

    second_candidates = build_ingestion_candidates(
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

    third_candidates = build_ingestion_candidates(
        updated_scan_results,
        state,
        max_cases_per_run=None,
    )
    assert len(third_candidates) == 1
    assert third_candidates[0].new_execution_ids == ["101.1-1"]


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

    result = ingest_case_with_retries(
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

    result = ingest_case_with_retries(
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
    ) -> dict[str, object]:
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

    exit_code_first = run_ingestor(
        config,
        metadata_locator=lambda *_: {},
        sleep_fn=lambda *_: None,
        post_request_fn=fake_post_request,
    )
    exit_code_second = run_ingestor(
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


def test_build_case_scan_results_is_deterministic() -> None:
    grouped = {
        "/performance_archive/case_b": ["200.1-1"],
        "/performance_archive/case_a": ["100.1-1", "101.1-1"],
    }

    results = build_case_scan_results(grouped)

    assert [result.case_path for result in results] == [
        "/performance_archive/case_a",
        "/performance_archive/case_b",
    ]
