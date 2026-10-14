"""Metadata-only archive and staging traversal."""

import gzip
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
