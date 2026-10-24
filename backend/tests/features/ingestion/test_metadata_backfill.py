"""Metadata-only archive and staging traversal."""

import argparse
import gzip
import json
import logging
import urllib.error
from argparse import Namespace
from functools import partial
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 -- register ORM relationship targets for isolated tests
from app.features.catalog.enums import ArtifactKind
from app.features.catalog.models import Artifact, Execution, MetadataChange
from app.features.ingestion.metadata_backfill import MetadataUpdate, update_metadata
from app.features.ingestion.v3_classification import V3_SIMULATIONS
from app.scripts.ingestion.backfill import metadata
from app.scripts.ingestion.backfill.metadata import _execution_paths, _read_execution
from tests.fixtures.continuation_case import stage_continuation_case


@pytest.fixture
def caplog(caplog, monkeypatch):
    """Capture backfill logs despite Alembic disabling existing loggers."""
    logger = metadata.ingestion_logger
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.INFO, logger=logger.name)

    return caplog


def _request_stub(record, calls, api, token, route, payload=None):
    calls.append((route, payload))

    return {"records": [record]} if payload is None else {"outcome": "changed"}


def _read_execution_stub(record, path, machine, fields):
    return Namespace(
        machine="pm-cpu",
        case_name="case",
        hpc_username="alice",
        execution_id=record["execution_id"],
        simulation_start_date="2020-01-01" if path.name == "stage" else "2021-01-01",
        simulation_end_date=None,
        run_script_path=None,
    )


def _unreadable_execution(*args):
    raise OSError("unreadable")


@pytest.mark.parametrize(
    "source",
    [
        "/global/homes/user/E3SM",
        "ssh://git@github.com/owner/repo.git",
    ],
)
def test_repository_repair_reads_archive_provenance(tmp_path, source):
    case = stage_continuation_case(tmp_path)
    execution = sorted(case.iterdir())[0]
    config = execution / f"GIT_CONFIG.{execution.name}.gz"
    with gzip.open(config, "wt") as stream:
        stream.write(f'[remote "origin"]\n    url = {source}\n')
    parsed = _read_execution(execution, "chrysalis", ["git-repository"])
    record = {
        "case_name": parsed.case_name,
        "hpc_username": parsed.hpc_username,
        "execution_id": parsed.execution_id,
        "error": None,
        "values": {"git_repository_source": "https://untrusted.example/"},
        "directories": [{"kind": "archive", "path": str(execution)}],
    }
    values = metadata._observed_values(
        record,
        Namespace(machine="chrysalis", sources="archive", fields=["git-repository"]),
    )
    assert values == {"git_repository_source": source}
    config.unlink()
    with pytest.raises(ValueError, match="Missing repository source"):
        _read_execution(execution, "chrysalis", ["git-repository"])


def test_repository_repair_rejects_conflicting_sources():
    with pytest.raises(ValueError, match="Conflicting source values"):
        metadata._consistent_values(
            [
                {"git_repository_source": "/local/repo"},
                {"git_repository_source": "https://github.com/owner/repo"},
            ],
            ["git_repository_source"],
        )


@pytest.mark.parametrize(
    "argument,alias",
    [("-res arcticx4", "arcticx4"), ("--res=arcticx4", "arcticx4"), ("", None)],
)
def test_grid_repair_reads_sources_not_stored_values(tmp_path, argument, alias):
    case = stage_continuation_case(tmp_path)
    execution = sorted(case.iterdir())[0]
    for path in execution.glob("CaseDocs.*/README.case.*.gz"):
        with gzip.open(path, "wt") as stream:
            stream.write(f"create_newcase {argument}\n")
    parsed = _read_execution(execution, "chrysalis", ["grid"])
    record = {
        "case_name": parsed.case_name,
        "hpc_username": parsed.hpc_username,
        "execution_id": parsed.execution_id,
        "error": None,
        "values": {"grid_long_name": "untrusted", "grid_alias": "also-untrusted"},
        "directories": [{"kind": "archive", "path": str(execution)}],
    }
    values = metadata._observed_values(
        record, Namespace(machine="chrysalis", sources="archive", fields=["grid"])
    )

    assert values["grid_long_name"].startswith("a%ne30np4.pg2_l%r05_")
    assert values["grid_alias"] == alias
    assert set(values) == {"grid_long_name", "grid_alias"}


@pytest.mark.parametrize("source", ["readme", "xml-file", "xml-value"])
def test_grid_repair_requires_readable_sources(tmp_path, source):
    execution = sorted(stage_continuation_case(tmp_path).iterdir())[0]
    if source == "readme":
        next(execution.glob("CaseDocs.*/README.case.*.gz")).unlink()
    else:
        path = next(execution.glob("CaseDocs.*/env_build.xml.*.gz"))
        if source == "xml-file":
            path.unlink()
        else:
            with gzip.open(path, "wt") as stream:
                stream.write("<config />")

    with pytest.raises(ValueError, match="Missing"):
        _read_execution(execution, "chrysalis", ["grid"])


def test_grid_repair_rejects_null_alias_conflict():
    with pytest.raises(ValueError, match="Conflicting source values for grid_alias"):
        metadata._consistent_values(
            [{"grid_alias": "alias"}, {"grid_alias": None}], ["grid_alias"]
        )


@pytest.mark.parametrize(
    "argument,alias",
    [("-compset F20TR-GHG", "F20TR-GHG"), ("--compset=1850_EAM_ELM", None), ("", None)],
)
def test_component_repair_reads_sources_not_stored_values(tmp_path, argument, alias):
    case = stage_continuation_case(tmp_path)
    execution = sorted(case.iterdir())[0]
    for path in execution.glob("CaseDocs.*/README.case.*.gz"):
        with gzip.open(path, "wt") as stream:
            stream.write(f"create_newcase {argument}\n")
    parsed = _read_execution(execution, "chrysalis", ["component-set"])
    record = {
        "case_name": parsed.case_name,
        "hpc_username": parsed.hpc_username,
        "execution_id": parsed.execution_id,
        "error": None,
        "values": {"compset_long_name": "untrusted", "compset_alias": "also-untrusted"},
        "directories": [{"kind": "archive", "path": str(execution)}],
    }
    values = metadata._observed_values(
        record,
        Namespace(machine="chrysalis", sources="archive", fields=["component-set"]),
    )

    assert values["compset_long_name"].startswith("20TRSOI_EAM%")
    assert values["compset_alias"] == alias
    assert set(values) == {"compset_long_name", "compset_alias"}


@pytest.mark.parametrize("source", ["readme", "xml-value"])
def test_component_repair_requires_readable_sources(tmp_path, source):
    case = stage_continuation_case(tmp_path)
    execution = sorted(case.iterdir())[0]
    if source == "readme":
        next(execution.glob("CaseDocs.*/README.case.*.gz")).unlink()
    else:
        path = next(execution.glob("CaseDocs.*/env_case.xml.*.gz"))
        with gzip.open(path, "rt") as stream:
            content = stream.read()
        with gzip.open(path, "wt") as stream:
            stream.write(
                "\n".join(
                    line for line in content.splitlines() if 'id="COMPSET"' not in line
                )
            )

    with pytest.raises(ValueError, match="Missing"):
        _read_execution(execution, "chrysalis", ["component-set"])


def test_component_repair_rejects_null_alias_conflict(tmp_path, monkeypatch):
    paths = [tmp_path / "one", tmp_path / "two"]
    for path in paths:
        path.mkdir()
    parsed = Namespace(
        case_name="case",
        hpc_username="alice",
        execution_id="1.1-1",
        simulation_start_date=None,
        simulation_end_date=None,
        run_script_path=None,
        compset_long_name="1850_EAM_ELM",
        compset_alias="F20TR-GHG",
    )
    observations = [parsed, Namespace(**{**vars(parsed), "compset_alias": None})]
    monkeypatch.setattr(
        metadata, "_read_execution", partial(_next_component_observation, observations)
    )
    record = {
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": "1.1-1",
        "error": None,
        "directories": [{"kind": "archive", "path": str(path)} for path in paths],
    }

    with pytest.raises(ValueError, match="Conflicting source values for compset_alias"):
        metadata._observed_values(
            record,
            Namespace(machine="chrysalis", sources="archive", fields=["component-set"]),
        )


def _next_component_observation(observations, *args):
    return observations.pop(0)


def test_component_alias_comparison_ignores_case_and_preserves_first_spelling():
    observations = [{"compset_alias": "F20TR-GHG"}, {"compset_alias": "f20tr-ghg"}]

    assert metadata._consistent_values(observations, ["compset_alias"]) == {
        "compset_alias": "F20TR-GHG"
    }


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
        v3=False,
        archive_start="2025-02",
        archive_end="2025-02",
        case_name="case",
        hpc_username="alice",
    )
    assert list(_execution_paths(staging, "staging", args)) == [staged]
    assert list(_execution_paths(archive, "archive", args)) == [recent]

    args.case_name = "other"
    assert list(_execution_paths(staging, "staging", args)) == []


@pytest.mark.parametrize(
    "excluded_layout",
    [
        "performance_archive_2026_10_15_10_03_11/COMPLETED/alice/case",
        "performance_archive_2026_10_15_10_03_11/FAILED/alice/case",
        "pace-exps-test/exp1",
        "alice/case/extra",
        "alice",
        "",
    ],
)
def test_staging_scan_only_visits_user_case_execution_layout(
    tmp_path, monkeypatch, excluded_layout
):
    lid = "123.250101-000000"
    execution = tmp_path / "alice" / "case" / lid
    execution.mkdir(parents=True)
    (execution / "CaseDocs" / lid).mkdir(parents=True)
    excluded = tmp_path / excluded_layout / lid
    excluded.mkdir(parents=True)
    args = _source_args(case_name=None, hpc_username=None)
    events = []
    monkeypatch.setattr(metadata, "_log_event", partial(_capture_log, events))
    monkeypatch.setattr(metadata, "DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES", 1)

    assert list(_execution_paths(tmp_path, "staging", args)) == [execution]
    visited = [
        fields["current_dir"]
        for event, fields in events
        if event == "backfill_scan_progress"
    ]
    assert visited == [
        str(tmp_path),
        str(tmp_path / "alice"),
        str(tmp_path / "alice" / "case"),
        str(execution),
    ]


@pytest.mark.parametrize("missing", ["case_docs_env_case", "e3sm_timing"])
def test_missing_identity_is_incomplete_without_guessing(tmp_path, capsys, missing):
    execution = tmp_path / "alice" / "case" / "123.250101-000000"
    execution.mkdir(parents=True)
    if missing == "e3sm_timing":
        docs = execution / "CaseDocs.123.250101-000000"
        docs.mkdir()
        with gzip.open(docs / "env_case.xml.123.250101-000000.gz", "wt") as stream:
            stream.write("<config/>")

    with pytest.raises(metadata._IncompleteExecutionError, match=missing):
        _read_execution(execution, "perlmutter", [])

    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 0
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["outcome"] == "skipped_incomplete"
    assert missing in output[0]["error"]
    assert output[-1]["skipped_incomplete"] == 1
    assert output[-1]["failed"] == 0


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


@pytest.mark.parametrize("source", ["staging", "archive"])
@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("unmatched_machine", [None, "muller"])
def test_bootstrap_routes_mixed_machine_sources(
    tmp_path, monkeypatch, capsys, source, apply, unmatched_machine
):
    root = tmp_path
    if source == "archive":
        root = root / "2025-01" / "performance_archive_2025_01_01_00_00_00"
    paths = {}
    for name, alias in (
        ("perlmutter", "pm-gpu"),
        ("muller", "muller-gpu"),
        ("alvarez", "alvarez-cpu"),
    ):
        execution = root / "alice" / f"case_{name}" / "123.250101-000000"
        _write_backfill_identity(execution, alias)
        paths[name] = str(execution)
    args = _source_args(
        sources=source,
        staging_root=tmp_path,
        archive_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
        apply=apply,
    )
    calls = []
    monkeypatch.setattr(
        metadata, "_request", partial(_machine_request_stub, calls, unmatched_machine)
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 0
    assert {payload["machine_name"] for payload in calls} == set(paths)
    for payload in calls:
        assert payload["dry_run"] == (not apply)
        assert (
            payload["directories"][0]["execution_path"]
            == paths[payload["machine_name"]]
        )
        assert payload["directories"][0]["kind"] == source
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[-1] == {
        "matched": 3 - int(unmatched_machine is not None),
        "skipped_no_owner": int(unmatched_machine is not None),
        "skipped_incomplete": 0,
        "failed": 0,
    }
    if unmatched_machine:
        skipped = [
            item for item in output[:-1] if item["outcome"] == "skipped_no_owner"
        ]
        assert [item["path"] for item in skipped] == [paths[unmatched_machine]]


@pytest.mark.parametrize("machine", [None, "", "   "])
def test_bootstrap_missing_machine_remains_failure(
    tmp_path, monkeypatch, capsys, machine
):
    execution = tmp_path / "alice" / "case" / "123.250101-000000"
    _write_backfill_identity(execution, machine)
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )
    calls = []
    monkeypatch.setattr(
        metadata, "_request", partial(_machine_request_stub, calls, None)
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "Source machine is missing" in output[0]["error"]
    assert output[-1]["failed"] == 1
    assert output[-1]["skipped_incomplete"] == 0
    assert calls == []


def test_bootstrap_unknown_machine_api_error_is_not_a_skip(
    tmp_path, monkeypatch, capsys
):
    execution = tmp_path / "alice" / "case" / "123.250101-000000"
    _write_backfill_identity(execution, "unknown-machine")
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )
    calls = []
    monkeypatch.setattr(metadata, "_request", partial(_unknown_machine_request, calls))

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    assert calls[0]["machine_name"] == "unknown-machine"
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["outcome"] == "failed"
    assert output[-1]["failed"] == 1
    assert output[-1]["skipped_no_owner"] == 0


@pytest.mark.parametrize("apply", [False, True])
def test_bootstrap_batches_by_machine_with_per_path_outcomes(
    tmp_path, monkeypatch, capsys, apply
):
    for index in range(7):
        _write_backfill_identity(
            tmp_path / "alice" / f"case_{index}" / "125.250101-000000",
            "pm-cpu" if index % 2 == 0 else "muller-gpu",
        )
    monkeypatch.setattr(metadata, "DISCOVERY_RESULT_BATCH_SIZE", 2)
    calls = []

    def request(api, token, route, payload):
        calls.append(payload)
        return {
            "unresolved": [
                d for d in payload["directories"] if d["case_name"] == "case_2"
            ]
        }

    monkeypatch.setattr(metadata, "_request", request)
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        apply=apply,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 0
    assert len(calls) == 4
    assert all(1 <= len(p["directories"]) <= 2 for p in calls)
    assert all(p["dry_run"] == (not apply) for p in calls)
    for payload in calls:
        for directory in payload["directories"]:
            index = int(directory["case_name"].split("_")[-1])
            assert payload["machine_name"] == (
                "perlmutter" if index % 2 == 0 else "muller"
            )
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(output[:-1]) == 7
    assert output[-1] == {
        "matched": 6,
        "skipped_no_owner": 1,
        "skipped_incomplete": 0,
        "failed": 0,
    }
    assert [
        Path(item["path"]).parent.name
        for item in output[:-1]
        if item["outcome"] == "skipped_no_owner"
    ] == ["case_2"]


def test_bootstrap_failed_batch_reports_every_execution(tmp_path, monkeypatch, capsys):
    for index in range(3):
        _write_backfill_identity(
            tmp_path / "alice" / f"case_{index}" / "125.250101-000000", "pm-cpu"
        )
    calls = []
    monkeypatch.setattr(metadata, "_request", partial(_unknown_machine_request, calls))
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(calls) == 1
    assert len(output[:-1]) == 3
    assert all(
        item["outcome"] == "failed" and "Machine not found" in item["error"]
        for item in output[:-1]
    )
    assert output[-1]["failed"] == 3


def test_bootstrap_flushes_pending_observations_after_walk_error(
    tmp_path, monkeypatch, capsys
):
    execution = tmp_path / "alice" / "case" / "125.250101-000000"
    _write_backfill_identity(execution, "pm-cpu")

    def paths(*args):
        yield execution
        raise PermissionError("Cannot traverse remaining directories")

    calls = []
    monkeypatch.setattr(metadata, "_execution_paths", paths)
    monkeypatch.setattr(
        metadata, "_request", partial(_machine_request_stub, calls, None)
    )
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[-1]["matched"] == 1
    assert output[-1]["failed"] == 1
    assert len(calls) == 1


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
    row = Execution(id=uuid4(), simulation_start_date="1850-01-01")
    unrelated = Artifact(kind=ArtifactKind.OUTPUT, uri="/keep")
    row.artifacts = [unrelated]
    editor = uuid4()
    dry = _update_payload(row)
    db = Session()

    result = update_metadata(db, row, dry, editor)
    assert set(result["changes"]) == {"run_script"}
    assert row.artifacts == [unrelated]
    assert not db.new

    dry.dry_run = False
    update_metadata(db, row, dry, editor)
    assert row.simulation_start_date == "1850-01-01"
    assert row.artifacts[0] is unrelated
    assert row.artifacts[1].uri == "/case/run.sh"

    dry.overwrite = True
    update_metadata(db, row, dry, editor)
    assert row.simulation_start_date == "2020-01-01"
    assert update_metadata(db, row, dry, editor)["outcome"] == "unchanged"
    history = list(db.new)
    assert all(isinstance(item, MetadataChange) for item in history)
    assert {item.field_name for item in history} == {
        "artifacts",
        "simulation_start_date",
    }
    assert len(history) == 2
    assert all(
        item.editor_id == editor and item.entity_id == row.id for item in history
    )
    assert all(item.reason == "Metadata backfill" for item in history)
    dates = next(item for item in history if item.field_name == "simulation_start_date")
    assert (dates.old_value, dates.new_value) == ("1850-01-01", "2020-01-01")
    scripts = next(item for item in history if item.field_name == "artifacts")
    assert scripts.old_value == [
        {
            "kind": "output",
            "uri": "/keep",
            "label": None,
            "checksum": None,
            "sizeBytes": None,
        }
    ]
    assert scripts.new_value[-1]["uri"] == "/case/run.sh"
    assert dates.changed_at == row.updated_at
    db.close()


def test_overwrite_script_history_preserves_full_artifact_values():
    script = Artifact(
        kind=ArtifactKind.RUN_SCRIPT,
        uri="/old/run.sh",
        label="Run script",
        checksum="old-checksum",
        size_bytes=123,
    )
    row = Execution(id=uuid4(), artifacts=[script])
    request = _update_payload(row, overwrite=True, dry_run=False)
    request.fields = ["run-script"]
    request.expected.run_script = script.uri
    with Session() as db:
        update_metadata(db, row, request, uuid4())
        change = next(iter(db.new))
        assert change.field_name == "artifacts"
        assert change.old_value[0] == {
            "kind": "run_script",
            "uri": "/old/run.sh",
            "label": "Run script",
            "checksum": "old-checksum",
            "sizeBytes": 123,
        }
        assert change.new_value[0] == {
            "kind": "run_script",
            "uri": "/case/run.sh",
            "label": "Run script",
            "checksum": None,
            "sizeBytes": None,
        }


def test_stale_update_rejected_before_any_write():
    row = Execution(id=uuid4(), simulation_start_date="1900-01-01")
    with pytest.raises(ValueError, match="changed"):
        update_metadata(
            None, row, _update_payload(row, overwrite=True, dry_run=False), uuid4()
        )
    assert row.artifacts == []
    assert row.simulation_start_date == "1900-01-01"


def test_database_first_uses_mappings_and_detects_conflicts(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    archive = tmp_path / "archive"
    stage.mkdir()
    archive.mkdir()
    record = {
        "record_id": str(uuid4()),
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": "123.250101-000000",
        "values": {},
        "error": None,
        "directories": [
            {"kind": "archive", "path": str(stage)},
            {"kind": "archive", "path": str(archive)},
        ],
    }
    calls = []

    monkeypatch.setattr(metadata, "_request", partial(_request_stub, record, calls))
    monkeypatch.setattr(
        metadata, "_read_execution", partial(_read_execution_stub, record)
    )
    args = Namespace(
        v3=False,
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
    row = Execution(id=uuid4(), simulation_start_date="1850-01-01")
    request = _update_payload(row)
    request.values.simulation_end_date = "2030-01-01"
    with pytest.raises(ValueError, match="different interval"):
        update_metadata(None, row, request, uuid4())


def test_unreadable_mapping_prevents_update(tmp_path, monkeypatch):
    record = {
        "error": None,
        "directories": [{"kind": "staging", "path": str(tmp_path)}],
    }
    monkeypatch.setattr(metadata, "_read_execution", _unreadable_execution)
    args = Namespace(sources="both", machine="perlmutter", fields=["simulation-dates"])
    with pytest.raises(ValueError, match="Cannot safely backfill"):
        metadata._observed_values(record, args)


@pytest.mark.parametrize("archive_exists", [False, True])
@pytest.mark.parametrize("staging_exists", [False, True])
def test_both_selects_archive_before_staging(
    tmp_path, monkeypatch, archive_exists, staging_exists
):
    archive = tmp_path / "archive"
    staging = tmp_path / "stage"
    for path, exists in ((archive, archive_exists), (staging, staging_exists)):
        if exists:
            path.mkdir()
    record = {
        "error": None,
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": "123.250101-000000",
        "directories": [
            {"kind": "staging", "path": str(staging)},
            {"kind": "archive", "path": str(archive)},
            {"kind": "archive", "path": str(tmp_path / "missing-archive")},
        ],
    }
    reads = []

    def read(path, machine, fields):
        reads.append(path)
        return _read_execution_stub(record, path, machine, fields)

    monkeypatch.setattr(metadata, "_read_execution", read)
    args = Namespace(sources="both", machine="perlmutter", fields=["simulation-dates"])

    if not archive_exists and not staging_exists:
        with pytest.raises(ValueError, match="No available mapped source directories"):
            metadata._observed_values(record, args)
        assert reads == []
    else:
        expected = "2021-01-01" if archive_exists else "2020-01-01"
        assert metadata._observed_values(record, args) == {
            "simulation_start_date": expected
        }
        assert reads == [archive if archive_exists else staging]


@pytest.mark.parametrize("sources", ["archive", "staging"])
def test_explicit_metadata_source_does_not_fallback(tmp_path, monkeypatch, sources):
    selected = tmp_path / sources
    other = tmp_path / ("staging" if sources == "archive" else "archive")
    other.mkdir()
    record = {
        "error": None,
        "directories": [
            {"kind": sources, "path": str(selected)},
            {
                "kind": "staging" if sources == "archive" else "archive",
                "path": str(other),
            },
        ],
    }
    reads = []

    def read(path, machine, fields):
        reads.append(path)
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(metadata, "_read_execution", read)
    args = Namespace(sources=sources, machine="perlmutter", fields=["run-script"])
    with pytest.raises(ValueError, match="Cannot safely backfill"):
        metadata._observed_values(record, args)
    assert reads == [selected]


@pytest.mark.parametrize(
    "failure",
    [
        "permission",
        "parse",
        "identity",
        "missing-identity",
        "disappeared",
        "no-metadata",
    ],
)
def test_selected_archive_failure_does_not_fallback(tmp_path, monkeypatch, failure):
    archive = tmp_path / "archive"
    staging = tmp_path / "stage"
    archive.mkdir()
    staging.mkdir()
    record = {
        "error": None,
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": "123.250101-000000",
        "directories": [
            {"kind": "archive", "path": str(archive)},
            {"kind": "staging", "path": str(staging)},
        ],
    }
    reads = []

    def read(path, machine, fields):
        reads.append(path)
        if failure == "permission":
            raise PermissionError("denied")
        if failure == "parse":
            raise ValueError("invalid metadata")
        if failure == "missing-identity":
            raise metadata._IncompleteExecutionError("Missing identity file")
        if failure == "disappeared":
            raise FileNotFoundError(str(path))
        parsed = _read_execution_stub(record, path, machine, fields)
        if failure == "identity":
            parsed.case_name = "wrong"
        if failure == "no-metadata":
            parsed.simulation_start_date = None
        return parsed

    monkeypatch.setattr(metadata, "_read_execution", read)
    args = Namespace(sources="both", machine="perlmutter", fields=["simulation-dates"])
    message = (
        "No requested metadata"
        if failure == "no-metadata"
        else "Cannot safely backfill"
    )
    with pytest.raises(ValueError, match=message):
        metadata._observed_values(record, args)
    assert reads == [archive]


@pytest.mark.parametrize("failure", ["permission", "not-directory", "other-os-error"])
def test_archive_selection_errors_do_not_fallback(tmp_path, monkeypatch, failure):
    archive = tmp_path / "archive"
    staging = tmp_path / "stage"
    staging.mkdir()
    if failure == "not-directory":
        archive.touch()
    else:
        original_stat = Path.stat

        def checked_stat(path, *args, **kwargs):
            if path == archive:
                if failure == "permission":
                    raise PermissionError("denied")
                raise OSError("storage unavailable")
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", checked_stat)

    directories = [
        {"kind": "archive", "path": str(archive)},
        {"kind": "staging", "path": str(staging)},
    ]
    with pytest.raises(ValueError, match="Cannot safely backfill"):
        metadata._preferred_metadata_paths(directories)


def test_archive_selection_rejects_mount_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("OLD_PERF_SOURCE_ROOT", str(tmp_path))
    directories = [
        {"kind": "archive", "path": "/OLD_PERF/../outside"},
        {"kind": "staging", "path": str(tmp_path)},
    ]

    with pytest.raises(ValueError, match="escapes configured root"):
        metadata._preferred_metadata_paths(directories)


@pytest.mark.parametrize(
    "mount,variable,kind,layout",
    [
        (
            "/performance_archive",
            "PERF_SOURCE_ROOT",
            "staging",
            "performance_archive_2026_10_15_10_03_11/COMPLETED",
        ),
        ("/OLD_PERF", "OLD_PERF_SOURCE_ROOT", "archive", "2026-10/snapshot"),
    ],
)
def test_database_first_reads_legacy_mount_from_host_root(
    tmp_path, monkeypatch, mount, variable, kind, layout
):
    relative = Path(layout) / "alice" / "case" / "123.250101-000000"
    execution = tmp_path / relative
    _write_backfill_identity(execution, "pm-cpu")
    docs = execution / f"CaseDocs.{execution.name}"
    with gzip.open(docs / f"env_run.xml.{execution.name}.gz", "wt") as stream:
        stream.write('<config><entry id="RUN_STARTDATE" value="2020-01-01"/></config>')
    monkeypatch.setenv(variable, str(tmp_path))
    record = {
        "case_name": "case",
        "hpc_username": "alice",
        "execution_id": execution.name,
        "error": None,
        "directories": [{"kind": kind, "path": str(Path(mount) / relative)}],
    }
    args = Namespace(sources="both", machine="perlmutter", fields=["simulation-dates"])

    assert metadata._observed_values(record, args) == {
        "simulation_start_date": "2020-01-01"
    }
    record["case_name"] = "wrong-owner"
    with pytest.raises(
        ValueError, match="Source identity does not match database owner"
    ):
        metadata._observed_values(record, args)


@pytest.mark.parametrize(
    "mount,variable",
    [
        ("/performance_archive", "PERF_SOURCE_ROOT"),
        ("/OLD_PERF", "OLD_PERF_SOURCE_ROOT"),
    ],
)
def test_source_path_requires_absolute_root_and_preserves_prefix_boundary(
    monkeypatch, mount, variable
):
    path = f"{mount}/alice/case/execution"
    monkeypatch.delenv(variable, raising=False)
    assert metadata._source_path(path) == Path(path)
    monkeypatch.setenv(variable, "relative/root")
    with pytest.raises(ValueError, match=f"{variable} must be an absolute path"):
        metadata._source_path(path)
    monkeypatch.setenv(variable, "/host/root")
    assert metadata._source_path(path) == Path("/host/root/alice/case/execution")
    for unchanged in ("/host/root/alice/case/execution", f"{mount}_other/execution"):
        assert metadata._source_path(unchanged) == Path(unchanged)
    with pytest.raises(ValueError, match="escapes configured root"):
        metadata._source_path(f"{mount}/../outside")


def test_database_first_missing_identity_remains_failure(tmp_path, monkeypatch, capsys):
    record = {
        "record_id": str(uuid4()),
        "error": None,
        "directories": [{"kind": "staging", "path": str(tmp_path)}],
    }
    calls = []
    args = _source_args(
        sources="staging",
        machine="perlmutter",
        fields=["simulation-dates"],
        case_name=None,
        hpc_username=None,
    )
    monkeypatch.setattr(metadata, "_request", partial(_request_stub, record, calls))

    assert metadata._backfill_metadata(args, "https://example.test", "token") == 1
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["outcome"] == "failed"
    assert "Missing identity file" in output[0]["error"]
    assert output[-1] == {"failed": 1}
    assert len(calls) == 1


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


def test_v3_defaults_reuse_archive_scope(monkeypatch):
    _set_source_environment(monkeypatch)
    monkeypatch.delenv("OLD_PERF_ARCHIVE_ROOT")
    monkeypatch.delenv("ARCHIVE_YEAR_START")
    args = _source_args(v3=True, machine="chrysalis", sources="archive")

    metadata._resolve_source_defaults(args)

    assert str(args.archive_root) == metadata.CHRYSALIS_ARCHIVE_ROOT
    assert args.archive_start == metadata.V3_ARCHIVE_YEAR_START
    assert args.archive_end == "2024-12"


def test_v3_defaults_preserve_environment_and_cli_overrides(monkeypatch, tmp_path):
    _set_source_environment(monkeypatch)
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2023-01")
    args = _source_args(v3=True, machine="chrysalis", sources="archive")

    metadata._resolve_source_defaults(args)

    assert str(args.archive_root) == "/configured/archive"
    assert args.archive_start == "2023-01"
    args.archive_root = tmp_path
    args.archive_start = "2022-01"
    args.archive_end = "2022-12"
    metadata._resolve_source_defaults(args)

    assert args.archive_root == tmp_path
    assert (args.archive_start, args.archive_end) == ("2022-01", "2022-12")


@pytest.mark.parametrize("sources", ["staging", "archive"])
def test_v3_discovery_filters_cases_and_preserves_case_user_bounds(tmp_path, sources):
    case_name = V3_SIMULATIONS[0]
    paths = {}
    for month in ("2023-12", "2024-01", "2025-01"):
        root = tmp_path
        if sources == "archive":
            snapshot = f"performance_archive_{month.replace('-', '_')}_01_00_00_00"
            root = root / month / snapshot / "COMPLETED"
        for username in ("alice", "bob"):
            for name in (case_name, V3_SIMULATIONS[1], "unrelated"):
                execution = root / username / name / "123.250101-000000"
                execution.mkdir(parents=True, exist_ok=True)
                paths[month, username, name] = execution
    args = _source_args(
        v3=True,
        archive_start=metadata.V3_ARCHIVE_YEAR_START,
        archive_end="2024-12",
        case_name=None,
        hpc_username="alice",
    )

    found = list(_execution_paths(tmp_path, sources, args))
    assert set(found) == {
        paths["2024-01", "alice", name] for name in V3_SIMULATIONS[:2]
    }
    args.case_name = case_name
    assert list(_execution_paths(tmp_path, sources, args)) == [
        paths["2024-01", "alice", case_name]
    ]


@pytest.mark.parametrize(
    "machine,case_name,message",
    [
        ("perlmutter", None, "--v3 requires --machine chrysalis"),
        ("chrysalis", "unrelated", "must be a documented v3 case"),
    ],
)
def test_v3_rejects_invalid_scope(capsys, machine, case_name, message):
    args = _source_args(v3=True, machine=machine, case_name=case_name)

    with pytest.raises(SystemExit):
        metadata._validate_sources(argparse.ArgumentParser(), args)

    assert message in capsys.readouterr().err


def test_v3_bootstrap_keeps_machine_identity_check(tmp_path):
    execution = tmp_path / "alice" / V3_SIMULATIONS[0] / "123.250101-000000"
    _write_backfill_identity(execution, "pm-cpu")
    args = _source_args(v3=True, machine="chrysalis")

    with pytest.raises(ValueError, match="Machine mismatch"):
        metadata._bootstrap_observation(execution, "archive", args)


@pytest.mark.parametrize("apply", [False, True])
def test_v3_database_first_filters_pages_and_uses_mapped_paths(
    monkeypatch, tmp_path, apply
):
    record = {
        "record_id": str(uuid4()),
        "case_name": V3_SIMULATIONS[0],
        "hpc_username": "alice",
        "execution_id": "123.250101-000000",
        "values": {},
        "error": None,
        "directories": [{"kind": "archive", "path": str(tmp_path)}],
    }
    pages = iter([[{"case_name": "unrelated"}] * 100, [record]])
    calls = []
    reads = []
    args = _source_args(
        v3=True,
        machine="chrysalis",
        fields=["simulation-dates"],
        case_name=None,
        hpc_username=None,
        overwrite=False,
        apply=apply,
    )
    monkeypatch.setattr(metadata, "_request", partial(_v3_request_stub, pages, calls))
    monkeypatch.setattr(
        metadata, "_read_execution", partial(_v3_read_stub, record, reads)
    )

    assert metadata._backfill_metadata(args, "https://example.test", "token") == 0
    assert "offset=0" in calls[0][0]
    assert "offset=100" in calls[1][0]
    assert len(calls) == 3
    assert calls[-1][1]["case_name"] == record["case_name"]
    assert calls[-1][1]["dry_run"] == (not apply)
    assert reads == [(tmp_path, "chrysalis", ["simulation-dates"])]


def test_main_accepts_v3_and_reports_scope(monkeypatch, capsys):
    _set_source_environment(monkeypatch)
    monkeypatch.delenv("ARCHIVE_YEAR_START")
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://example.test")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "hidden-token")
    monkeypatch.setattr(
        "sys.argv",
        [
            "metadata",
            "--machine",
            "chrysalis",
            "--v3",
            "--fields",
            "source-directories",
        ],
    )
    captured = []
    monkeypatch.setattr(metadata, "_bootstrap", partial(_capture_command, captured))

    assert metadata.main() == 0
    scope = json.loads(capsys.readouterr().out)
    assert scope["v3"] is True
    assert scope["archive_start"] == metadata.V3_ARCHIVE_YEAR_START
    assert scope["dry_run"] is True
    assert captured[0].v3 is True


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

    assert metadata._bootstrap(args, "https://example.test", "token") == 0
    assert not any(event == "backfill_scan_no_matches" for event, _ in events)
    assert (
        next(fields for event, fields in events if event == "backfill_scan_completed")[
            "matching_executions"
        ]
        == 1
    )
    output = capsys.readouterr().out
    assert '"outcome": "skipped_no_owner"' in output
    assert json.loads(output.splitlines()[-1]) == {
        "matched": 0,
        "skipped_no_owner": 1,
        "skipped_incomplete": 0,
        "failed": 0,
    }


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
    for number in (123, 124, 125, 126):
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
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == {
        "matched": 1,
        "skipped_no_owner": 1,
        "skipped_incomplete": 1,
        "failed": 1,
    }
    assert "RUN_SUMMARY Metadata backfill" in caplog.text
    assert "RUN_SUMMARY Existing owners matched: 1" in caplog.text
    assert "RUN_SUMMARY Skipped without existing owner: 1" in caplog.text
    assert "RUN_SUMMARY Skipped incomplete executions: 1" in caplog.text
    assert "RUN_SUMMARY Read/parse/API/scan failures: 1" in caplog.text
    assert "RUN_SUMMARY Status: failure" in caplog.text
    assert "RUN_SUMMARY Exit code: 1" in caplog.text
    assert ("Database writes: disabled (dry run)" in caplog.text) == (not apply)


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("source", ["staging", "archive"])
@pytest.mark.parametrize("numbers", [(123,), (124,), (123, 124), (123, 124, 125)])
def test_expected_bootstrap_skips_succeed(
    tmp_path, monkeypatch, capsys, caplog, apply, source, numbers
):
    case = tmp_path / "alice" / "case"
    if source == "archive":
        case = (
            tmp_path
            / "2025-01"
            / "performance_archive_2025_01_01_00_00_00"
            / "COMPLETED"
            / "alice"
            / "case"
        )
    for number in numbers:
        (case / f"{number}.250101-000000").mkdir(parents=True)
    args = _source_args(
        sources=source,
        staging_root=tmp_path,
        archive_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
        apply=apply,
    )
    calls = []
    monkeypatch.setattr(metadata, "_read_execution", _summary_read_stub)
    monkeypatch.setattr(metadata, "_request", partial(_capture_summary_request, calls))

    assert metadata._bootstrap(args, "https://example.test", "token") == 0
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[-1] == {
        "matched": int(125 in numbers),
        "skipped_no_owner": int(124 in numbers),
        "skipped_incomplete": int(123 in numbers),
        "failed": 0,
    }
    assert [item["outcome"] for item in output[:-1]] == [
        {123: "skipped_incomplete", 124: "skipped_no_owner", 125: "matched"}[number]
        for number in numbers
    ]
    assert all(item["dry_run"] == (not apply) for item in output[:-1])
    assert len(calls) == int(any(number != 123 for number in numbers))
    assert all(payload["dry_run"] == (not apply) for payload in calls)
    assert "RUN_SUMMARY Status: success" in caplog.text
    assert "RUN_SUMMARY Exit code: 0" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Missing identity file from another validation"),
        ValueError("Machine mismatch"),
        ValueError("Malformed metadata"),
        ValueError("Ambiguous identity"),
        PermissionError("Permission denied"),
        metadata.IngestionRequestError(
            "API unavailable", status_code=503, transient=False
        ),
    ],
)
@pytest.mark.parametrize("phase", ["read", "request"])
def test_bootstrap_actual_errors_still_fail(
    tmp_path, monkeypatch, capsys, error, phase
):
    (tmp_path / "alice" / "case" / "125.250101-000000").mkdir(parents=True)
    args = _source_args(
        sources="staging",
        staging_root=tmp_path,
        machine="perlmutter",
        case_name=None,
        hpc_username=None,
    )
    monkeypatch.setattr(metadata, "_read_execution", _summary_read_stub)
    monkeypatch.setattr(
        metadata,
        "_read_execution" if phase == "read" else "_request",
        partial(_raise_bootstrap_error, error),
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["outcome"] == "failed"
    assert output[-1]["failed"] == 1
    assert output[-1]["skipped_incomplete"] == 0


def test_bootstrap_traversal_error_still_fails(tmp_path, capsys):
    args = _source_args(
        sources="staging",
        staging_root=tmp_path / "missing",
        case_name=None,
        hpc_username=None,
    )

    assert metadata._bootstrap(args, "https://example.test", "token") == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["failed"] == 1


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


def _write_backfill_identity(execution, machine):
    docs = execution / f"CaseDocs.{execution.name}"
    docs.mkdir(parents=True)
    machine_entry = (
        f'<entry id="MACH" value="{machine}"/>' if machine is not None else ""
    )
    with gzip.open(docs / f"env_case.xml.{execution.name}.gz", "wt") as stream:
        stream.write(
            f'<config><entry id="CASE" value="{execution.parent.name}"/>'
            f'{machine_entry}<entry id="REALUSER" value="alice"/></config>'
        )
    (execution / f"e3sm_timing.{execution.name}").write_text(f"LID: {execution.name}\n")


def _machine_request_stub(calls, unmatched_machine, api, token, route, payload):
    calls.append(payload)

    return {
        "unresolved": payload["directories"]
        if payload["machine_name"] == unmatched_machine
        else []
    }


def _unknown_machine_request(calls, api, token, route, payload):
    calls.append(payload)
    raise metadata.IngestionRequestError(
        "Machine not found.", status_code=404, transient=False
    )


def _summary_read_stub(path, machine, fields):
    if path.name.startswith("123."):
        raise metadata._IncompleteExecutionError(
            f"Missing identity file case_docs_env_case: {path}"
        )
    if path.name.startswith("126."):
        raise ValueError(f"Malformed metadata: {path}")

    return Namespace(
        machine="pm-cpu", case_name="case", hpc_username="alice", execution_id=path.name
    )


def _summary_request_stub(api, token, route, payload):
    return {
        "unresolved": [
            directory
            for directory in payload["directories"]
            if directory["execution_id"].startswith("124.")
        ]
    }


def _capture_summary_request(calls, api, token, route, payload):
    calls.append(payload)

    return _summary_request_stub(api, token, route, payload)


def _raise_bootstrap_error(error, *args):
    raise error


def _terminal_request_failure(*args, **kwargs):
    raise metadata.IngestionRequestError(
        "API unavailable", status_code=503, transient=False
    )


def _page_request_stub(pages, api, token, route, payload=None):
    return {"records": next(pages)}


def _capture_log(events, event, fields):
    events.append((event, fields))


def _unresolved_request(*args, **kwargs):
    payload = kwargs.get("payload", args[-1])
    return {"unresolved": payload["directories"]}


def _transient_request_failure(*args, **kwargs):
    raise urllib.error.URLError("hidden-token")


def _source_args(**overrides):
    values = {
        "v3": False,
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


def _v3_request_stub(pages, calls, api, token, route, payload=None):
    calls.append((route, payload))

    return {"records": next(pages)} if payload is None else {"outcome": "changed"}


def _v3_read_stub(record, reads, path, machine, fields):
    reads.append((path, machine, fields))

    return Namespace(
        machine="chrysalis",
        case_name=record["case_name"],
        hpc_username=record["hpc_username"],
        execution_id=record["execution_id"],
        simulation_start_date="1850-01-01",
        simulation_end_date=None,
        run_script_path=None,
    )
