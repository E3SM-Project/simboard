"""Metadata-only archive and staging traversal."""

import argparse
import gzip
import urllib.error
from argparse import Namespace
from datetime import date
from functools import partial
from uuid import uuid4

import pytest

import app.models  # noqa: F401 -- register ORM relationship targets for isolated tests
from app.features.catalog.enums import ArtifactKind
from app.features.catalog.models import Artifact, Execution
from app.features.ingestion.metadata_backfill import MetadataUpdate, update_metadata
from app.scripts.ingestion.backfill import metadata
from app.scripts.ingestion.backfill.metadata import _execution_paths, _read_execution


def _request_stub(record, calls, api, token, route, payload=None):
    calls.append((route, payload))

    return {"records": [record]} if payload is None else {"outcome": "changed"}


def _read_execution_stub(record, path, machine, fields):
    return Namespace(
        case_name="case",
        hpc_username="alice",
        execution_id=record["execution_id"],
        simulation_start_date="2020-01-01" if str(path) == "/stage" else "2021-01-01",
        simulation_end_date=None,
        run_script_path=None,
    )


def _unreadable_execution(*args):
    raise OSError("unreadable")


def test_both_layouts_and_archive_bounds(tmp_path):
    staging = tmp_path / "staging"
    archive = tmp_path / "archive"
    lid = "123.250101-000000"
    staged = staging / "alice" / "case" / lid
    staged.mkdir(parents=True)
    old = (
        archive
        / "2025-01"
        / "performance_archive_2025_01_01_00_00_00"
        / "alice"
        / "case"
        / lid
    )
    old.mkdir(parents=True)
    recent = (
        archive
        / "2025-02"
        / "performance_archive_2025_02_01_00_00_00"
        / "COMPLETED"
        / "alice"
        / "case"
        / lid
    )
    recent.mkdir(parents=True)
    args = Namespace(
        archive_start="2025-02",
        archive_end="2025-02",
        case_name="case",
        hpc_username="alice",
    )
    assert list(_execution_paths(staging, "staging", args)) == [staged]
    assert list(_execution_paths(archive, "archive", args)) == [recent]

    args.case_name = "other"
    assert list(_execution_paths(staging, "staging", args)) == []


def test_missing_identity_fails_without_guessing(tmp_path):
    with pytest.raises(ValueError, match="Missing identity"):
        _read_execution(tmp_path, "perlmutter", [])


def test_targeted_parsing_does_not_require_full_ingestion(tmp_path):
    tmp_path = tmp_path / "123.250101-000000"
    tmp_path.mkdir()
    docs = tmp_path / "CaseDocs.123.250101-000000"
    docs.mkdir()
    with gzip.open(docs / "env_case.xml.123.250101-000000.gz", "wt") as stream:
        stream.write(
            '<config><entry id="CASE" value="case"/><entry id="MACH" value="pm-cpu"/><entry id="REALUSER" value="alice"/></config>'
        )
    (tmp_path / "e3sm_timing.123.250101-000000").write_text("LID: 123.250101-000000\n")
    parsed = _read_execution(tmp_path, "perlmutter", [])

    assert (parsed.case_name, parsed.hpc_username, parsed.execution_id) == (
        "case",
        "alice",
        "123.250101-000000",
    )
    with pytest.raises(ValueError, match="Machine mismatch"):
        _read_execution(tmp_path, "chrysalis", [])


def _update_payload(row, **kwargs):
    return MetadataUpdate(
        machine_name="perlmutter",
        record_id=row.id,
        case_name="case",
        hpc_username="alice",
        execution_id="123.250101-000000",
        fields=["simulation-dates", "run-script"],
        values={"simulation_start_date": "2020-01-01", "run_script": "/case/run.sh"},
        expected={"simulation_start_date": "1850-01-01"},
        **kwargs,
    )


def test_dry_run_fill_missing_overwrite_and_idempotency():
    row = Execution(id=uuid4(), simulation_start_date=date(1850, 1, 1))
    unrelated = Artifact(kind=ArtifactKind.OUTPUT, uri="/keep")
    row.artifacts = [unrelated]
    editor = uuid4()
    dry = _update_payload(row)

    result = update_metadata(None, row, dry, editor)
    assert set(result["changes"]) == {"run_script"}
    assert row.artifacts == [unrelated]

    dry.dry_run = False
    update_metadata(None, row, dry, editor)
    assert row.simulation_start_date == date(1850, 1, 1)
    assert row.artifacts[0] is unrelated
    assert row.artifacts[1].uri == "/case/run.sh"

    dry.overwrite = True
    update_metadata(None, row, dry, editor)
    assert row.simulation_start_date == date(2020, 1, 1)
    assert update_metadata(None, row, dry, editor)["outcome"] == "unchanged"


def test_stale_update_rejected_before_any_write():
    row = Execution(id=uuid4(), simulation_start_date=date(1900, 1, 1))
    with pytest.raises(ValueError, match="changed"):
        update_metadata(
            None, row, _update_payload(row, overwrite=True, dry_run=False), uuid4()
        )
    assert row.artifacts == []
    assert row.simulation_start_date == date(1900, 1, 1)


def test_database_first_uses_mappings_and_detects_conflicts(monkeypatch):
    record = {
        "record_id": str(uuid4()),
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": "123.250101-000000",
        "values": {},
        "error": None,
        "directories": [
            {"kind": "staging", "path": "/stage"},
            {"kind": "archive", "path": "/archive"},
        ],
    }
    calls = []

    monkeypatch.setattr(metadata, "_request", partial(_request_stub, record, calls))
    monkeypatch.setattr(
        metadata, "_read_execution", partial(_read_execution_stub, record)
    )
    args = Namespace(
        machine="perlmutter",
        case_name="case",
        hpc_username="alice",
        sources="both",
        fields=["simulation-dates"],
        overwrite=True,
        apply=False,
    )
    assert metadata._backfill_metadata(args, "https://example.test/api/v1", "test") == 1
    assert len(calls) == 1

    record["directories"] = record["directories"][:1]
    assert metadata._backfill_metadata(args, "https://example.test/api/v1", "test") == 0
    assert calls[-1][1]["dry_run"] is True


def test_metadata_schema_rejects_unknown_fields():
    row = Execution(id=uuid4())
    payload = _update_payload(row).model_dump()
    payload["values"]["status"] = "completed"
    with pytest.raises(ValueError):
        MetadataUpdate.model_validate(payload)


def test_fill_dates_cannot_mix_intervals():
    row = Execution(id=uuid4(), simulation_start_date=date(1850, 1, 1))
    request = _update_payload(row)
    request.values.simulation_end_date = date(2030, 1, 1)
    with pytest.raises(ValueError, match="different interval"):
        update_metadata(None, row, request, uuid4())


def test_unreadable_mapping_prevents_update(monkeypatch):
    record = {"error": None, "directories": [{"kind": "staging", "path": "/missing"}]}
    monkeypatch.setattr(metadata, "_read_execution", _unreadable_execution)
    args = Namespace(sources="both", machine="perlmutter", fields=["simulation-dates"])
    with pytest.raises(ValueError, match="Cannot safely backfill"):
        metadata._observed_values(record, args)


@pytest.mark.parametrize("sources", ["staging", "archive", "both"])
def test_source_defaults_apply_only_to_selected_sources(monkeypatch, sources):
    _set_source_environment(monkeypatch)
    args = _source_args(sources=sources)

    metadata._resolve_source_defaults(args)

    assert str(args.staging_root) == (
        "/configured/staging" if sources != "archive" else "None"
    )
    assert str(args.archive_root) == (
        "/configured/archive" if sources != "staging" else "None"
    )
    assert args.archive_start == ("2024-01" if sources != "staging" else None)
    assert args.archive_end == ("2024-12" if sources != "staging" else None)


def test_cli_source_settings_override_environment(monkeypatch, tmp_path):
    _set_source_environment(monkeypatch)
    args = _source_args(
        staging_root=tmp_path / "stage",
        archive_root=tmp_path / "archive",
        archive_start="2023-01",
        archive_end="2023-12",
    )

    metadata._resolve_source_defaults(args)

    assert args.staging_root == tmp_path / "stage"
    assert args.archive_root == tmp_path / "archive"
    assert (args.archive_start, args.archive_end) == ("2023-01", "2023-12")


def test_archive_start_uses_site_default_and_end_remains_optional(monkeypatch):
    _set_source_environment(monkeypatch)
    monkeypatch.delenv("ARCHIVE_YEAR_START")
    monkeypatch.delenv("ARCHIVE_YEAR_END")
    args = _source_args()

    metadata._resolve_source_defaults(args)

    assert args.archive_start == "2025-01"
    assert args.archive_end is None


def test_database_first_does_not_inherit_filesystem_settings(monkeypatch):
    _set_source_environment(monkeypatch)
    monkeypatch.setenv("ARCHIVE_YEAR_START", "invalid")
    args = _source_args(fields=["simulation-dates", "run-script"])

    metadata._resolve_source_defaults(args)
    metadata._validate_sources(argparse.ArgumentParser(), args)

    assert args.staging_root is None
    assert args.archive_root is None
    assert args.archive_start is None
    assert args.archive_end is None


@pytest.mark.parametrize("root", ["", "   "])
def test_missing_configured_root_fails_validation(monkeypatch, root):
    monkeypatch.setenv("PERF_ARCHIVE_ROOT", root)
    args = _source_args(sources="staging")
    metadata._resolve_source_defaults(args)

    with pytest.raises(SystemExit):
        metadata._validate_sources(argparse.ArgumentParser(), args)


@pytest.mark.parametrize("start,end", [("invalid", None), ("2025-02", "2025-01")])
def test_invalid_configured_archive_bounds_fail(monkeypatch, start, end):
    _set_source_environment(monkeypatch)
    monkeypatch.setenv("ARCHIVE_YEAR_START", start)
    monkeypatch.setenv("ARCHIVE_YEAR_END", end or "")
    args = _source_args()
    metadata._resolve_source_defaults(args)

    with pytest.raises(SystemExit):
        metadata._validate_sources(argparse.ArgumentParser(), args)


def test_main_reports_resolved_scope_without_credentials(monkeypatch, capsys):
    _set_source_environment(monkeypatch)
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://example.test")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "hidden-token")
    monkeypatch.setattr(
        "sys.argv",
        ["metadata", "--machine", "perlmutter", "--fields", "source-directories"],
    )
    captured = []
    monkeypatch.setattr(metadata, "_bootstrap", partial(_capture_command, captured))

    assert metadata.main() == 0
    output = capsys.readouterr().out
    assert "/configured/staging" in output
    assert "/configured/archive" in output
    assert "2024-01" in output
    assert "hidden-token" not in output
    assert captured[0].apply is False


def test_abbreviated_machine_cannot_override_launcher_selection(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "metadata",
            "--machine",
            "perlmutter",
            "--fields",
            "source-directories",
            "--mach",
            "chrysalis",
        ],
    )

    with pytest.raises(SystemExit):
        metadata.main()


@pytest.mark.parametrize("case_name", ["case", "no-match"])
def test_scan_logs_progress_even_when_filters_match_nothing(
    tmp_path, monkeypatch, case_name
):
    execution = tmp_path / "alice" / "case" / "123.250101-000000"
    execution.mkdir(parents=True)
    args = _source_args(case_name=case_name, hpc_username="alice")
    events = []
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))
    monkeypatch.setattr(metadata, "DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES", 2)

    paths = list(metadata._execution_paths(tmp_path, "staging", args))

    assert paths == ([execution] if case_name == "case" else [])
    assert events[0][0] == "backfill_scan_started"
    progress = [fields for event, fields in events if event == "backfill_scan_progress"]
    assert [p["directories_visited"] for p in progress] == [2, 4]
    completed = next(
        fields for event, fields in events if event == "backfill_scan_completed"
    )
    assert completed["traversal_complete"] is True
    assert completed["directories_visited"] == 4
    assert completed["matching_executions"] == len(paths)
    assert completed["source"] == "staging"
    assert completed["duration_seconds"] >= 0
    assert (events[-1][0] == "backfill_scan_no_matches") == (not paths)


def test_failed_scan_logs_incomplete_completion(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))
    args = _source_args(case_name=None, hpc_username=None)

    with pytest.raises(ValueError, match="not a directory"):
        list(metadata._execution_paths(tmp_path / "missing", "staging", args))

    assert [event for event, _ in events] == [
        "backfill_scan_started",
        "backfill_scan_completed",
    ]
    assert events[-1][1]["traversal_complete"] is False


def test_filesystem_matches_are_distinct_from_unresolved_owners(
    tmp_path, monkeypatch, capsys
):
    execution = tmp_path / "alice" / "case" / "123.250101-000000"
    execution.mkdir(parents=True)
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name="case",
        hpc_username="alice",
        apply=False,
    )
    record = {"execution_id": execution.name}
    events = []
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))
    monkeypatch.setattr(
        metadata, "_read_execution", partial(_read_execution_stub, record)
    )
    monkeypatch.setattr(metadata, "_request", _unresolved_request)

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    assert not any(event == "backfill_scan_no_matches" for event, _ in events)
    assert (
        next(fields for event, fields in events if event == "backfill_scan_completed")[
            "matching_executions"
        ]
        == 1
    )
    output = capsys.readouterr().out
    assert '"outcome": "unresolved"' in output
    assert '"matched": 0, "failed": 1' in output


def test_retry_log_is_sanitized_and_does_not_include_payload(monkeypatch, caplog):
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "hidden-token")
    monkeypatch.setattr(metadata.urllib.request, "urlopen", _transient_request_failure)
    delays = []
    monkeypatch.setattr(metadata.time, "sleep", delays.append)

    with pytest.raises(metadata.IngestionRequestError):
        metadata._request(
            "https://example.test",
            "hidden-token",
            "secret-route",
            {"token": "hidden-token"},
        )

    retry_logs = [
        r.getMessage() for r in caplog.records if "backfill_api_retry" in r.getMessage()
    ]
    assert len(retry_logs) == 2
    assert len(delays) == 2
    assert all("delay_seconds=" in message for message in retry_logs)
    assert "hidden-token" not in caplog.text
    assert "secret-route" not in caplog.text


def test_scan_logs_reuse_credential_redaction(tmp_path, monkeypatch, caplog):
    root = tmp_path / "hidden-token"
    root.mkdir()
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "hidden-token")
    args = _source_args(case_name=None, hpc_username=None)

    assert list(metadata._execution_paths(root, "staging", args)) == []
    assert "backfill_scan_no_matches" in caplog.text
    assert "[REDACTED]" in caplog.text
    assert "hidden-token" not in caplog.text


def test_database_page_progress_preserves_summary(monkeypatch, capsys):
    calls = []
    events = []
    record = {"record_id": str(uuid4()), "error": "missing source"}
    args = _source_args(machine="perlmutter", case_name=None, hpc_username=None)
    monkeypatch.setattr(metadata, "_request", partial(_request_stub, record, calls))
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))

    assert metadata._backfill_metadata(args, "https://example.test", "token") == 1
    assert [event for event, _ in events] == [
        "backfill_page_started",
        "backfill_page_completed",
    ]
    assert events[0][1] == {"offset": 0, "records": 1}
    assert events[1][1] == {"offset": 0, "records": 1, "failed_total": 1}
    assert '"failed": 1' in capsys.readouterr().out


def test_page_logs_identify_cumulative_failures(monkeypatch, capsys):
    events = []
    record = {"record_id": str(uuid4()), "error": "missing source"}
    pages = iter([[record] * 100, [record]])
    args = _source_args(machine="perlmutter", case_name=None, hpc_username=None)
    monkeypatch.setattr(metadata, "_request", partial(_page_request_stub, pages))
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))

    assert metadata._backfill_metadata(args, "https://example.test", "token") == 1
    completed = [
        fields for event, fields in events if event == "backfill_page_completed"
    ]
    assert completed == [
        {"offset": 0, "records": 100, "failed_total": 100},
        {"offset": 100, "records": 1, "failed_total": 101},
    ]
    assert '"failed": 101' in capsys.readouterr().out


@pytest.mark.parametrize("apply", [False, True])
def test_readable_directory_summary_separates_unresolved_and_failures(
    tmp_path, monkeypatch, capsys, caplog, apply
):
    for number in (123, 124, 125):
        (tmp_path / "alice" / "case" / f"{number}.250101-000000").mkdir(parents=True)
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
        apply=apply,
    )
    monkeypatch.setattr(metadata, "_read_execution", _summary_read_stub)
    monkeypatch.setattr(metadata, "_request", _summary_request_stub)

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    assert '"matched": 1, "failed": 2' in capsys.readouterr().out
    assert "RUN_SUMMARY Metadata backfill" in caplog.text
    assert "RUN_SUMMARY Existing owners matched: 1" in caplog.text
    assert "RUN_SUMMARY Unresolved owners: 1" in caplog.text
    assert "RUN_SUMMARY Read/parse/API/scan failures: 1" in caplog.text
    assert "RUN_SUMMARY Status: failure" in caplog.text
    assert "RUN_SUMMARY Exit code: 1" in caplog.text
    assert ("Database writes: disabled (dry run)" in caplog.text) == (not apply)


@pytest.mark.parametrize(
    "apply,label", [(False, "Records with planned changes"), (True, "Records changed")]
)
def test_readable_metadata_summary_uses_mode_appropriate_labels(caplog, apply, label):
    args = Namespace(apply=apply)

    metadata._log_metadata_summary(
        args, {"changed": 2, "unchanged": 3}, 0, metadata.time.monotonic()
    )

    assert f"RUN_SUMMARY {label}: 2" in caplog.text
    assert "RUN_SUMMARY Records unchanged: 3" in caplog.text
    assert "RUN_SUMMARY Record/request failures: 0" in caplog.text
    assert "RUN_SUMMARY Status: success" in caplog.text
    assert "RUN_SUMMARY Exit code: 0" in caplog.text


def test_metadata_fetch_failure_still_has_readable_summary(monkeypatch, caplog):
    args = _source_args(machine="perlmutter", case_name=None, hpc_username=None)
    monkeypatch.setattr(metadata, "_request", _terminal_request_failure)

    assert metadata._backfill_metadata(args, "https://example.test", "token") == 1
    assert "RUN_SUMMARY Record/request failures: 1" in caplog.text
    assert "RUN_SUMMARY Status: failure" in caplog.text


def _summary_read_stub(path, machine, fields):
    if path.name.startswith("123."):
        raise ValueError(f"Missing identity file case_docs_env_case: {path}")

    return Namespace(case_name="case", hpc_username="alice", execution_id=path.name)


def _summary_request_stub(api, token, route, payload):
    directory = payload["directories"][0]

    return {
        "unresolved": [directory]
        if directory["execution_id"].startswith("124.")
        else []
    }


def _terminal_request_failure(*args, **kwargs):
    raise metadata.IngestionRequestError(
        "API unavailable", status_code=503, transient=False
    )


def _page_request_stub(pages, api, token, route, payload=None):
    return {"records": next(pages)}


def _capture_log(events, event, fields):
    events.append((event, fields))


def _unresolved_request(*args, **kwargs):
    return {"unresolved": ["missing owner"]}


def _transient_request_failure(*args, **kwargs):
    raise urllib.error.URLError("hidden-token")


def _source_args(**overrides):
    values = {
        "fields": ["source-directories"],
        "apply": False,
        "sources": "both",
        "staging_root": None,
        "archive_root": None,
        "archive_start": None,
        "archive_end": None,
    }
    values.update(overrides)

    return Namespace(**values)


def _set_source_environment(monkeypatch):
    monkeypatch.setenv("PERF_ARCHIVE_ROOT", "/configured/staging")
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", "/configured/archive")
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2024-01")
    monkeypatch.setenv("ARCHIVE_YEAR_END", "2024-12")
    monkeypatch.setenv("SIMBOARD_DEFAULT_ARCHIVE_YEAR_START", "2025-01")


def _capture_command(captured, args, api, token):
    captured.append(args)

    return 0
