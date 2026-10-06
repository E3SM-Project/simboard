"""Source mappings from normal scans, without revisiting checkpointed snapshots."""

import json
from types import SimpleNamespace

import pytest

from app.scripts.ingestion import archive_source_directories as source_module
from app.scripts.ingestion import hpc_upload_archive_ingestor, nersc_archive_ingestor
from app.scripts.ingestion.archive_discovery import _scan_archive
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionRequestError,
    IngestorConfig,
)


def _config(root, *, scan_mode="staging", dry_run=False):
    return IngestorConfig(
        api_base_url="https://simboard.example",
        api_token="token",
        archive_root=root,
        machine_name="perlmutter",
        dry_run=dry_run,
        max_cases_per_run=None,
        max_attempts=2,
        request_timeout_seconds=30,
        scan_mode=scan_mode,
    )


@pytest.fixture
def parsed_metadata(monkeypatch):
    parsed = SimpleNamespace(
        case_name="actual-case",
        hpc_username="actual-user",
        machine="pm-cpu",
        execution_id="100.1-1",
    )
    monkeypatch.setattr(source_module, "_locate_metadata_files", lambda _: {})
    monkeypatch.setattr(source_module, "_parse_all_files", lambda *_: parsed)
    return parsed


@pytest.mark.parametrize(
    "runner", [nersc_archive_ingestor, hpc_upload_archive_ingestor]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_duplicate_only_scan_records_paths_without_upload(
    tmp_path,
    monkeypatch,
    parsed_metadata,
    runner,
    dry_run,
):
    case_path = tmp_path / "performance_archive" / "not-the-case-name"
    (case_path / "100.1-1").mkdir(parents=True)
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    monkeypatch.setattr(runner, "_fetch_ingestion_state", lambda *a, **kw: state)
    calls = []

    def record(*args, directories, **kwargs):
        calls.extend(directories)
        return {"status_code": 200, "body": {}}

    def upload(*args, **kwargs):
        pytest.fail("duplicate-only scan must not upload")

    assert (
        runner._run_ingestor(
            _config(case_path.parent, dry_run=dry_run),
            post_request_fn=upload,
            source_directory_post_request_fn=record,
        )
        == 0
    )
    assert len(calls) == (0 if dry_run else 1)
    if calls:
        assert calls[0].case_name == "actual-case"
        assert calls[0].hpc_username == "actual-user"
        assert calls[0].case_path == str(case_path)
        assert calls[0].execution_path == str(case_path / "100.1-1")
        assert calls[0].kind == "staging"


@pytest.mark.parametrize(
    "runner", [nersc_archive_ingestor, hpc_upload_archive_ingestor]
)
@pytest.mark.parametrize("fail_mapping", [False, True])
def test_archive_mappings_precede_checkpoints(
    tmp_path,
    monkeypatch,
    parsed_metadata,
    runner,
    fail_mapping,
):
    root = tmp_path / "OLD_PERF"
    snapshot_names = [
        "performance_archive_2025_01_01_00_00_00",
        "performance_archive_2025_01_02_00_00_00",
    ]
    case_paths = [
        root / "2025-01" / name / "COMPLETED" / "user" / "case"
        for name in snapshot_names
    ]
    for path in case_paths:
        (path / "100.1-1").mkdir(parents=True)
    state = {"cases": {str(case_paths[0]): {"processed_execution_ids": ["100.1-1"]}}}
    monkeypatch.setattr(runner, "_fetch_ingestion_state", lambda *a, **kw: state)
    monkeypatch.setattr(runner, "_fetch_archive_checkpoints", lambda *a, **kw: set())
    events = []
    mappings = []

    def record(*args, directories, **kwargs):
        events.append("mappings")
        if fail_mapping:
            raise IngestionRequestError("unresolved", status_code=409, transient=False)
        mappings.extend(directories)
        return {"status_code": 200, "body": {}}

    def checkpoint(*args, **kwargs):
        events.append("checkpoint")
        return {"status_code": 200, "body": {}}

    assert runner._run_ingestor(
        _config(root, scan_mode="archive"),
        source_directory_post_request_fn=record,
        checkpoint_post_request_fn=checkpoint,
    ) == int(fail_mapping)
    assert events == (["mappings"] if fail_mapping else ["mappings", "checkpoint"])
    if not fail_mapping:
        assert {entry.case_path for entry in mappings} == {
            str(path) for path in case_paths
        }
        assert all(entry.kind == "archive" for entry in mappings)


def test_checkpointed_directories_are_not_observed(tmp_path):
    root = tmp_path / "OLD_PERF"
    key = "2025-01/performance_archive_2025_01_01_00_00_00"
    (root / key / "case" / "100.1-1").mkdir(parents=True)
    visited = []
    _scan_archive(
        _config(root, scan_mode="archive"),
        {},
        metadata_locator=lambda _: pytest.fail(
            "checkpointed snapshots must not be visited"
        ),
        completed_snapshot_keys={key},
        observed_execution_paths=visited,
    )
    assert visited == []


def test_rejected_or_deferred_execution_needs_no_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(
        source_module, "_observe_source_directory", lambda *a: pytest.fail("no owner")
    )
    assert source_module._persist_visited_source_directories(
        [(tmp_path / "case", "100.1-1")],
        {},
        _config(tmp_path),
        lambda _: None,
    )


@pytest.mark.parametrize(
    "field,value",
    [("case_name", None), ("hpc_username", None), ("machine", "chrysalis")],
)
def test_invalid_identity_is_reported(
    tmp_path, monkeypatch, parsed_metadata, field, value
):
    events = []
    monkeypatch.setattr(
        source_module, "_log_event", lambda event, fields: events.append(event)
    )
    setattr(parsed_metadata, field, value)
    case_path = tmp_path / "case"
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    assert not source_module._persist_visited_source_directories(
        [(case_path, "100.1-1")],
        state,
        _config(tmp_path),
        lambda _: None,
    )
    assert events == ["source_directory_unresolved"]


def test_source_submission_retries_same_batch(tmp_path, parsed_metadata):
    case_path = tmp_path / "case"
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    calls = []
    sleeps = []

    def record(*args, directories, **kwargs):
        calls.append(directories)
        if len(calls) == 1:
            raise IngestionRequestError("retry", status_code=503, transient=True)
        return {"status_code": 200, "body": {}}

    assert source_module._persist_visited_source_directories(
        [(case_path, "100.1-1")],
        state,
        _config(tmp_path),
        sleeps.append,
        record,
    )
    assert calls[0] == calls[1]
    assert sleeps == [1]


@pytest.mark.parametrize(
    "runner", [nersc_archive_ingestor, hpc_upload_archive_ingestor]
)
def test_processed_but_missing_execution_is_reported_without_blocking_checkpoint(
    tmp_path,
    monkeypatch,
    parsed_metadata,
    runner,
):
    root = tmp_path / "OLD_PERF"
    case_path = root / "2025-01" / "performance_archive_2025_01_01_00_00_00" / "case"
    (case_path / "100.1-1").mkdir(parents=True)
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    monkeypatch.setattr(runner, "_fetch_ingestion_state", lambda *a, **kw: state)
    monkeypatch.setattr(runner, "_fetch_archive_checkpoints", lambda *a, **kw: set())
    events = []
    monkeypatch.setattr(
        source_module, "_log_event", lambda event, fields: events.append(event)
    )

    def record(*args, directories, **kwargs):
        return {
            "status_code": 200,
            "body": {
                "recorded_count": 0,
                "unresolved": [entry.model_dump(mode="json") for entry in directories],
            },
        }

    def checkpoint(*args, **kwargs):
        events.append("checkpoint")
        return {"status_code": 200, "body": {}}

    assert (
        runner._run_ingestor(
            _config(root, scan_mode="archive"),
            source_directory_post_request_fn=record,
            checkpoint_post_request_fn=checkpoint,
        )
        == 0
    )
    assert events == ["source_directory_unresolved", "checkpoint"]


def test_observed_paths_preserve_symlink_spelling(
    tmp_path, monkeypatch, parsed_metadata
):
    root = tmp_path / "performance_archive"
    (root / "case" / "100.1-1").mkdir(parents=True)
    alias = tmp_path / "observed-root"
    alias.symlink_to(root, target_is_directory=True)
    state = {"cases": {str(root / "case"): {"processed_execution_ids": ["100.1-1"]}}}
    visited = []
    config = _config(alias)
    _scan_archive(
        config, state, metadata_locator=lambda _: {}, observed_execution_paths=visited
    )
    assert visited == [(alias / "case", "100.1-1")]
    entries = []

    def record(*args, directories, **kwargs):
        entries.extend(directories)
        return {"status_code": 200, "body": {}}

    assert source_module._persist_visited_source_directories(
        visited, state, config, lambda _: None, record
    )
    assert entries[0].case_path == str(alias / "case")


def test_source_submission_http_payload(tmp_path, monkeypatch, parsed_metadata):
    directory = source_module._observe_source_directory(
        tmp_path / "case", "100.1-1", _config(tmp_path)
    )
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"recorded_count": 1}'

    def urlopen(request, timeout):
        requests.append(request)
        assert timeout == 30
        return Response()

    monkeypatch.setattr(source_module.urllib.request, "urlopen", urlopen)
    source_module._post_source_directories_request(
        "https://simboard.example/api/v1/ingestions/source-directories",
        "token",
        "perlmutter",
        directories=[directory],
        timeout_seconds=30,
    )
    assert requests[0].get_header("Authorization") == "Bearer token"
    assert json.loads(requests[0].data)["directories"] == [
        directory.model_dump(mode="json")
    ]
