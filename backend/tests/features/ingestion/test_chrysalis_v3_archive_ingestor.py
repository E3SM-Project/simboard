"""Tests for targeted Chrysalis E3SM v3 archive uploads."""

import json
import urllib.request
from pathlib import Path
from typing import Any

from app.scripts.ingestion import chrysalis_v3_archive_ingestor as v3_ingestor
from app.scripts.ingestion import hpc_upload_archive_ingestor as upload_ingestor
from app.scripts.ingestion import nersc_archive_ingestor as base_ingestor
from app.scripts.ingestion.nersc_archive_ingestor import (
    CaseCollectionLogData,
    IngestionRequestResponse,
    IngestorConfig,
    IngestorRunReport,
    _fresh_state,
)


def _config(archive_root: Path, *, dry_run: bool) -> IngestorConfig:
    return IngestorConfig(
        api_base_url="https://simboard.example",
        api_token="token",
        archive_root=archive_root,
        machine_name="chrysalis",
        dry_run=dry_run,
        max_cases_per_run=None,
        max_attempts=1,
        request_timeout_seconds=30,
        scan_mode="archive",
        archive_year_start="2024-01",
    )


def _populate_complete_report(report: IngestorRunReport) -> None:
    report.scan_completed = True
    report.discovery_stats = base_ingestor._new_discovery_stats()
    report.case_collection_data = {
        f"/lcrc/OLD_PERF/2024-01/snapshot/COMPLETED/user/{case_name}": (
            CaseCollectionLogData(case_path=case_name, execution_count_total=1)
        )
        for case_name in v3_ingestor.V3_CASE_NAMES
    }


class _FakeHttpResponse:
    status = 201

    def read(self) -> bytes:
        return json.dumps(
            {"created_count": 1, "duplicate_count": 0, "errors": []}
        ).encode()

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def test_documented_simulations_normalize_to_unique_case_names() -> None:
    assert len(v3_ingestor.V3_CASE_NAMES) == len(v3_ingestor.V3_SIMULATIONS)
    assert (
        v3_ingestor.V3_CASE_NAMES_BY_SIMULATION[
            "v3.LR.piClim-histall/v3.LR.piClim-histall_0101"
        ]
        == "v3.LR.piClim-histall_0101"
    )


def test_v3_case_filter_requires_exact_leaf_name() -> None:
    assert v3_ingestor._is_v3_case_path(Path("/archive/v3.LR.piControl"))
    assert not v3_ingestor._is_v3_case_path(Path("/archive/prefix-v3.LR.piControl"))
    assert not v3_ingestor._is_v3_case_path(Path("/archive/v3.LR.piControl-extra"))


def test_v3_config_forces_archive_mode_and_2024_lower_bound(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SCAN_MODE", "staging")
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2023-01")
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://simboard.example")
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", str(tmp_path / "OLD_PERF"))

    config = v3_ingestor._build_v3_config_from_env()

    assert config.scan_mode == "archive"
    assert config.archive_root == (tmp_path / "OLD_PERF").resolve()
    assert config.archive_year_start == "2024-01"
    assert config.machine_name == "chrysalis"


def test_v3_config_requires_remote_api_url(monkeypatch) -> None:
    monkeypatch.delenv("SIMBOARD_API_BASE_URL", raising=False)

    try:
        v3_ingestor._build_v3_config_from_env()
    except ValueError as exc:
        assert str(exc) == (
            "SIMBOARD_API_BASE_URL is required for remote Chrysalis uploads"
        )
    else:
        raise AssertionError("missing remote API URL must fail configuration")


def test_v3_summary_reports_paths_missing_and_execution_outcomes(
    monkeypatch,
) -> None:
    report = IngestorRunReport(scan_completed=True)
    stats = base_ingestor._new_discovery_stats()
    stats["execution_dirs_accepted"] = 4
    stats["rejected_existing_execution_ids"] = 3
    stats["rejected_incomplete_execution_ids"] = 2
    stats["rejected_invalid_execution_ids"] = 1
    stats["transient_execution_ids"] = 5
    stats["deferred_execution_ids"] = 6
    report.discovery_stats = stats
    matched_case_name = "v3.LR.piClim-histall_0101"
    first_path = f"/lcrc/OLD_PERF/2024-01/snapshot-a/COMPLETED/user/{matched_case_name}"
    second_path = (
        f"/lcrc/OLD_PERF/2024-02/snapshot-b/COMPLETED/user/{matched_case_name}"
    )
    report.case_collection_data = {
        first_path: CaseCollectionLogData(case_path=first_path),
        second_path: CaseCollectionLogData(case_path=second_path),
    }
    logged_events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        v3_ingestor,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
    )

    missing = v3_ingestor._log_v3_summary(report, dry_run=True)

    match_event = next(
        fields for event, fields in logged_events if event == "v3_case_match"
    )
    summary = next(
        fields for event, fields in logged_events if event == "v3_ingestion_summary"
    )
    assert match_event["case_paths"] == [first_path, second_path]
    assert len(missing) == len(v3_ingestor.V3_SIMULATIONS) - 1
    assert summary["execution_dirs_accepted"] == 4
    assert summary["rejected_existing_execution_ids"] == 3
    assert summary["rejected_incomplete_execution_ids"] == 2
    assert summary["rejected_invalid_execution_ids"] == 1
    assert summary["transient_execution_ids"] == 5
    assert summary["deferred_execution_ids"] == 6


def test_targeted_archive_run_filters_cases_and_skips_all_checkpoints(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    snapshot = (
        archive_root
        / "2024-01"
        / "performance_archive_2024_01_01_00_00_00"
        / "COMPLETED"
        / "user"
    )
    v3_execution = snapshot / "v3.LR.piControl" / "100.1-1"
    unrelated_execution = snapshot / "unrelated-case" / "200.1-1"
    old_v3_execution = (
        archive_root
        / "2023-12"
        / "performance_archive_2023_12_31_00_00_00"
        / "COMPLETED"
        / "user"
        / "v3.LR.piControl"
        / "300.1-1"
    )
    v3_execution.mkdir(parents=True)
    unrelated_execution.mkdir(parents=True)
    old_v3_execution.mkdir(parents=True)
    validated: list[str] = []
    captured_requests: list[urllib.request.Request] = []

    monkeypatch.setattr(
        upload_ingestor,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    def fail_checkpoint(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("targeted runner must not use archive checkpoints")

    monkeypatch.setattr(upload_ingestor, "_fetch_archive_checkpoints", fail_checkpoint)

    def post_discovery(*args: Any, **kwargs: Any) -> IngestionRequestResponse:
        return {"status_code": 201, "body": {}}

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_requests.append(request)
        assert timeout == 30
        return _FakeHttpResponse()

    monkeypatch.setattr(upload_ingestor.urllib.request, "urlopen", fake_urlopen)

    report = IngestorRunReport()
    exit_code = upload_ingestor._run_ingestor(
        _config(archive_root, dry_run=False),
        metadata_locator=lambda path: validated.append(path),
        discovery_post_request_fn=post_discovery,
        checkpoint_post_request_fn=fail_checkpoint,
        case_path_filter=v3_ingestor._is_v3_case_path,
        archive_checkpointing=False,
        run_report=report,
    )

    assert exit_code == 0
    assert validated == [str(v3_execution)]
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.full_url.endswith("/api/v1/ingestions/from-hpc-upload")
    assert request.headers["Content-type"].startswith("multipart/form-data;")
    assert isinstance(request.data, bytes)
    assert b'name="machine_name"\r\n\r\nchrysalis' in request.data
    assert str(v3_execution.parent).encode() in request.data
    assert b'filename="v3.LR.piControl-' in request.data
    assert b"unrelated-case" not in request.data
    assert b"300.1-1" not in request.data
    assert set(report.case_collection_data) == {str(v3_execution.parent)}


def test_targeted_dry_run_never_calls_write_functions(
    tmp_path: Path, monkeypatch
) -> None:
    archive_root = tmp_path / "OLD_PERF"
    execution = (
        archive_root
        / "2024-01"
        / "performance_archive_2024_01_01_00_00_00"
        / "COMPLETED"
        / "user"
        / "v3.LR.piControl"
        / "100.1-1"
    )
    execution.mkdir(parents=True)
    monkeypatch.setattr(
        upload_ingestor,
        "_fetch_ingestion_state",
        lambda *args, **kwargs: _fresh_state(),
    )

    def fail_write(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry run must not write")

    exit_code = upload_ingestor._run_ingestor(
        _config(archive_root, dry_run=True),
        metadata_locator=lambda *_: {},
        post_request_fn=fail_write,
        discovery_post_request_fn=fail_write,
        checkpoint_post_request_fn=fail_write,
        case_path_filter=v3_ingestor._is_v3_case_path,
        archive_checkpointing=False,
    )

    assert exit_code == 0


def test_v3_main_disables_checkpoints_and_succeeds_when_all_cases_match(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path, dry_run=True)
    captured_kwargs: dict[str, Any] = {}
    logged_events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(v3_ingestor, "_build_v3_config_from_env", lambda: config)
    monkeypatch.setattr(
        v3_ingestor,
        "_log_event",
        lambda event, fields=None: logged_events.append((event, fields or {})),
    )

    def fake_run(config: IngestorConfig, **kwargs: Any) -> int:
        captured_kwargs.update(kwargs)
        _populate_complete_report(kwargs["run_report"])
        return 0

    monkeypatch.setattr(v3_ingestor, "_run_upload_ingestor", fake_run)

    assert v3_ingestor.main() == 0
    assert captured_kwargs["archive_checkpointing"] is False
    assert captured_kwargs["case_path_filter"] is v3_ingestor._is_v3_case_path
    assert any(event == "v3_ingestion_summary" for event, _ in logged_events)


def test_v3_main_fails_reconciliation_when_case_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path, dry_run=True)
    monkeypatch.setattr(v3_ingestor, "_build_v3_config_from_env", lambda: config)
    monkeypatch.setattr(v3_ingestor, "_log_event", lambda *args, **kwargs: None)

    def fake_run(config: IngestorConfig, **kwargs: Any) -> int:
        report = kwargs["run_report"]
        _populate_complete_report(report)
        report.case_collection_data.pop(next(iter(report.case_collection_data)))
        return 0

    monkeypatch.setattr(v3_ingestor, "_run_upload_ingestor", fake_run)

    assert v3_ingestor.main() == 1
