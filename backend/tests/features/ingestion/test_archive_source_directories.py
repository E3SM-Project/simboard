"""Source mappings from normal scans, without revisiting checkpointed snapshots."""

import gzip
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.catalog.models import Case, Execution, SourceDirectory
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import UserRole
from app.main import app
from app.scripts.ingestion import archive_source_directories as source_module
from app.scripts.ingestion import hpc_upload_archive_ingestor, nersc_archive_ingestor
from app.scripts.ingestion.archive_discovery import _scan_archive
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionRequestError,
    IngestorConfig,
)
from tests.features.catalog.test_models import _create_dependencies
from tests.fixtures.continuation_case import (
    CASE_NAME,
    EXECUTIONS,
    stage_continuation_case,
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
@pytest.mark.parametrize("source_root", [None, Path("/host/performance_archive")])
def test_duplicate_only_scan_records_paths_without_upload(
    tmp_path,
    monkeypatch,
    parsed_metadata,
    runner,
    dry_run,
    source_root,
):
    root = tmp_path / "performance_archive"
    case_path = root / "user" / "not-the-case-name"
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
            replace(_config(root, dry_run=dry_run), source_root=source_root),
            post_request_fn=upload,
            source_directory_post_request_fn=record,
        )
        == 0
    )
    assert len(calls) == (0 if dry_run else 1)
    if calls:
        assert calls[0].case_name == "actual-case"
        assert calls[0].hpc_username == "actual-user"
        expected = (source_root or root) / case_path.relative_to(root)
        assert calls[0].case_path == str(expected)
        assert calls[0].execution_path == str(expected / "100.1-1")
        assert calls[0].kind == "staging"


@pytest.mark.parametrize(
    "runner", [nersc_archive_ingestor, hpc_upload_archive_ingestor]
)
@pytest.mark.parametrize("fail_mapping", [False, True])
@pytest.mark.parametrize("source_root", [None, Path("/host/OLD_PERF")])
def test_archive_mappings_precede_checkpoints(
    tmp_path,
    monkeypatch,
    parsed_metadata,
    runner,
    fail_mapping,
    source_root,
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
        replace(_config(root, scan_mode="archive"), source_root=source_root),
        source_directory_post_request_fn=record,
        checkpoint_post_request_fn=checkpoint,
    ) == int(fail_mapping)
    assert events == (["mappings"] if fail_mapping else ["mappings", "checkpoint"])
    if not fail_mapping:
        assert {entry.case_path for entry in mappings} == {
            str((source_root or root) / path.relative_to(root)) for path in case_paths
        }
        assert all(entry.kind == "archive" for entry in mappings)


@pytest.mark.parametrize(
    "tail", ["../outside/case", "../performance_archive-other/case"]
)
def test_source_mapping_rejects_paths_outside_root(tmp_path, parsed_metadata, tail):
    root = tmp_path / "performance_archive"
    config = replace(_config(root), source_root=Path("/host/performance_archive"))
    with pytest.raises(ValueError):
        source_module._observe_source_directory(root / tail, "100.1-1", config)


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
    [
        ("case_name", None),
        ("hpc_username", None),
        ("machine", None),
        ("machine", ""),
        ("machine", "  "),
    ],
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


@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError])
def test_source_file_errors_preserve_other_observations(
    tmp_path, monkeypatch, parsed_metadata, error_type
):
    case_path = tmp_path / "case"
    execution_ids = ["100.1-1", "100.1-2"]
    state = {"cases": {str(case_path): {"processed_execution_ids": execution_ids}}}
    events = []
    monkeypatch.setattr(
        source_module,
        "_log_event",
        lambda event, fields: events.append((event, fields)),
    )

    def locate(path):
        if path == str(case_path / execution_ids[0]):
            raise error_type("source metadata unavailable")
        return {}

    monkeypatch.setattr(source_module, "_locate_metadata_files", locate)
    observations = []

    def record(*args, directories, **kwargs):
        observations.extend(directories)
        return {"status_code": 200, "body": {}}

    result = source_module._persist_visited_source_directories(
        [(case_path, execution_id) for execution_id in execution_ids],
        state,
        _config(tmp_path),
        lambda _: None,
        record,
    )

    assert result is (error_type is FileNotFoundError)
    assert [entry.execution_path for entry in observations] == (
        [str(case_path / execution_ids[1])] if result else []
    )
    assert events == [
        (
            "source_directory_unresolved",
            {
                "execution_path": str(case_path / execution_ids[0]),
                "error": "source metadata unavailable",
            },
        )
    ]


def test_local_staging_ingests_only_ready_siblings(tmp_path, monkeypatch, db, client):
    user, _, _ = _create_dependencies(db)
    user.role = UserRole.SERVICE_ACCOUNT
    db.flush()
    monkeypatch.setitem(app.dependency_overrides, current_active_user, lambda: user)
    root = tmp_path / "performance_archive"
    case_path = stage_continuation_case(root / "user")
    running_id = next(iter(EXECUTIONS))
    status_file = case_path / running_id / f"CaseStatus.{running_id}.gz"
    starting = "2026-10-20 10:00:00: case.run starting\n"
    with gzip.open(status_file, "wt") as stream:
        stream.write(starting)
    submissions = []

    @contextmanager
    def urlopen(request, timeout):
        payload = json.loads(request.data) if request.data else None
        if request.full_url.endswith("/from-path"):
            submissions.append(payload)
        response = client.request(request.get_method(), request.full_url, json=payload)
        assert response.is_success, response.text
        yield SimpleNamespace(
            status=response.status_code, read=lambda: response.content
        )

    monkeypatch.setattr(source_module.urllib.request, "urlopen", urlopen)
    config = replace(_config(root), api_base_url="http://testserver")
    assert nersc_archive_ingestor._run_ingestor(config) == 0
    ready_ids = sorted(set(EXECUTIONS) - {running_id})
    assert submissions[0]["selected_execution_ids"] == ready_ids
    assert sorted(row.execution_id for row in db.query(Execution).all()) == ready_ids
    assert (
        db.query(Ingestion)
        .filter_by(source_reference=str(case_path))
        .one()
        .processed_execution_ids
        == ready_ids
    )

    # A repeated scan must not ingest the running sibling through the case path.
    assert nersc_archive_ingestor._run_ingestor(config) == 0
    assert len(submissions) == 1
    assert db.query(Execution).count() == len(ready_ids)

    with gzip.open(status_file, "wt") as stream:
        stream.write(starting + "2026-10-20 11:00:00: case.run success\n")
    assert nersc_archive_ingestor._run_ingestor(config) == 0
    assert submissions[1]["selected_execution_ids"] == [running_id]
    assert db.query(Execution).count() == len(EXECUTIONS)
    assert (
        db.query(Execution).filter_by(execution_id=running_id).one().status
        == "completed"
    )


@pytest.mark.parametrize(
    "runner", [nersc_archive_ingestor, hpc_upload_archive_ingestor]
)
@pytest.mark.parametrize("scan_mode", ["staging", "archive"])
def test_processed_incomplete_metadata_does_not_fail_run(
    tmp_path, monkeypatch, runner, scan_mode
):
    root = tmp_path / "performance_archive"
    case_path = root / "user" / "case"
    if scan_mode == "archive":
        root = tmp_path / "OLD_PERF"
        case_path = (
            root / "2025-01" / "performance_archive_2025_01_01_00_00_00" / "case"
        )
    (case_path / "100.1-1").mkdir(parents=True)
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    monkeypatch.setattr(runner, "_fetch_ingestion_state", lambda *a, **kw: state)
    monkeypatch.setattr(runner, "_fetch_archive_checkpoints", lambda *a, **kw: set())
    events = []
    monkeypatch.setattr(
        source_module, "_log_event", lambda event, fields: events.append(event)
    )

    def unexpected_request(*args, **kwargs):
        pytest.fail("processed incomplete execution must not upload or record a source")

    def checkpoint(*args, **kwargs):
        events.append("checkpoint")
        return {"status_code": 200, "body": {}}

    assert (
        runner._run_ingestor(
            _config(root, scan_mode=scan_mode),
            post_request_fn=unexpected_request,
            source_directory_post_request_fn=unexpected_request,
            checkpoint_post_request_fn=checkpoint,
        )
        == 0
    )
    assert events == ["source_directory_unresolved"] + (
        ["checkpoint"] if scan_mode == "archive" else []
    )


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
    machine_name, directory = source_module._observe_source_directory(
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
        machine_name,
        directories=[directory],
        timeout_seconds=30,
    )
    assert requests[0].get_header("Authorization") == "Bearer token"
    assert json.loads(requests[0].data)["directories"] == [
        directory.model_dump(mode="json")
    ]


@pytest.mark.parametrize("scan_mode", ["staging", "archive"])
def test_nersc_mixed_machine_scan_preserves_state_and_source_identity(
    tmp_path, monkeypatch, db, client, scan_mode
):
    user, _, _ = _create_dependencies(db)
    user.role = UserRole.SERVICE_ACCOUNT
    machines = {
        name: db.query(Machine).filter_by(name=name).one()
        for name in ("perlmutter", "muller", "alvarez")
    }
    scanner_machine = machines["perlmutter"]
    db.flush()
    monkeypatch.setitem(app.dependency_overrides, current_active_user, lambda: user)

    root = tmp_path / ("performance_archive" if scan_mode == "staging" else "OLD_PERF")
    snapshot_key = "2025-01/performance_archive_2025_01_01_00_00_00"
    scan_root = root if scan_mode == "staging" else root / snapshot_key
    case_paths = {}
    for machine_name, alias in (
        ("perlmutter", "pm-gpu"),
        ("muller", "muller-gpu"),
        ("alvarez", "alvarez-cpu"),
    ):
        case_root = scan_root / machine_name
        if scan_mode == "archive":
            case_root = scan_root / "UNKNOWN" / machine_name
        case_path = stage_continuation_case(case_root)
        case_paths[machine_name] = case_path
        for path in case_path.glob("*/CaseDocs.*/env_case.xml.*.gz"):
            with gzip.open(path, "rt") as stream:
                xml = stream.read()
            with gzip.open(path, "wt") as stream:
                stream.write(xml.replace('value="chrysalis"', f'value="{alias}"'))

    requests = []

    @contextmanager
    def urlopen(request, timeout):
        payload = json.loads(request.data) if request.data else None
        requests.append((request.get_method(), request.full_url, payload))
        response = client.request(request.get_method(), request.full_url, json=payload)
        assert response.is_success, response.text
        yield SimpleNamespace(
            status=response.status_code, read=lambda: response.content
        )

    monkeypatch.setattr(source_module.urllib.request, "urlopen", urlopen)
    config = replace(
        _config(root, scan_mode=scan_mode), api_base_url="http://testserver"
    )
    for _ in range(2):
        assert nersc_archive_ingestor._run_ingestor(config) == 0

    submissions = [
        payload for method, url, payload in requests if url.endswith("/from-path")
    ]
    assert len(submissions) == len(machines)
    assert all(payload["machine_name"] == "perlmutter" for payload in submissions)
    source_requests = [
        payload
        for method, url, payload in requests
        if url.endswith("/source-directories")
    ]
    assert len(source_requests) == len(machines) * (2 if scan_mode == "staging" else 1)
    for payload in source_requests:
        machine_name = payload["machine_name"]
        assert {entry["case_path"] for entry in payload["directories"]} == {
            str(case_paths[machine_name])
        }
        assert {entry["execution_id"] for entry in payload["directories"]} == set(
            EXECUTIONS
        )

    assert db.query(Execution).count() == len(machines) * len(EXECUTIONS)
    assert db.query(SourceDirectory).count() == len(machines) * (1 + len(EXECUTIONS))
    for machine_name, machine in machines.items():
        case = db.query(Case).filter_by(machine_id=machine.id, name=CASE_NAME).one()
        assert {entry.path for entry in case.source_directories} == {
            str(case_paths[machine_name])
        }
        for execution in case.executions:
            assert {entry.path for entry in execution.source_directories} == {
                str(case_paths[machine_name] / execution.execution_id)
            }
    ingestions = (
        db.query(Ingestion)
        .filter(Ingestion.source_reference.in_(map(str, case_paths.values())))
        .all()
    )
    assert len(ingestions) == len(machines)
    assert all(ingestion.machine_id == scanner_machine.id for ingestion in ingestions)
    state_requests = [url for method, url, payload in requests if "/state?" in url]
    assert len(state_requests) == 2
    assert all("machine_name=perlmutter" in url for url in state_requests)
    checkpoint_requests = [
        payload
        for method, url, payload in requests
        if method == "POST" and url.endswith("/archive-checkpoints")
    ]
    assert checkpoint_requests == (
        [
            {
                "machine_name": "perlmutter",
                "archive_name": root.name,
                "snapshots": [
                    {
                        "archive_month": "2025-01",
                        "snapshot_name": "performance_archive_2025_01_01_00_00_00",
                    }
                ],
            }
        ]
        if scan_mode == "archive"
        else []
    )


@pytest.mark.parametrize("machine_name", ["unknown-machine", "UNKNOWN", "muller-typo"])
def test_unknown_source_machine_is_not_reassigned(
    tmp_path, monkeypatch, parsed_metadata, machine_name
):
    parsed_metadata.machine = machine_name
    case_path = tmp_path / "case"
    state = {"cases": {str(case_path): {"processed_execution_ids": ["100.1-1"]}}}
    calls = []

    def record(endpoint, token, machine, **kwargs):
        calls.append(machine)
        raise IngestionRequestError(
            "Machine not found.", status_code=404, transient=False
        )

    assert not source_module._persist_visited_source_directories(
        [(case_path, "100.1-1")], state, _config(tmp_path), lambda _: None, record
    )
    assert calls == [machine_name.lower()]
