"""Case configuration and coverage policies, without relying on query order."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.features.catalog.case_summary import (
    simulation_coverage,
    summarize_case_executions,
)
from app.features.catalog.enums import ExecutionStatus
from app.features.catalog.models import Execution
from app.features.catalog.schemas import CaseDetailOut


def test_baselines_are_per_field_with_provenance_and_differences():
    first = _run("a", "hash", run_start_date=_date(1), grid_alias=None)
    tied = _run("b", "hash", run_start_date=_date(1), compset_alias="changed")
    later = _run("c", "hash", run_start_date=_date(2), grid_alias="later-grid")
    undated = _run("d", "hash", compset_alias="undated")
    result = summarize_case_executions([undated, later, tied, first])
    group = result["configuration_groups"][0]

    assert group.execution_ids == ["a", "b", "c", "d"]
    compset = group.configuration["compset_alias"]
    assert compset.source.execution_uuid == first.id
    assert compset.source.run_date == _date(1)
    assert [item.execution_id for item in compset.differences] == ["b", "d"]
    assert compset.differences[0].run_date == compset.source.run_date
    assert compset.differences[1].run_date is None
    grid = group.configuration["grid_alias"]
    assert grid.source.execution_id == "b"
    assert grid.source.value == "grid"
    assert grid.missing_execution_ids == ["a"]
    assert grid.differences[0].value == "later-grid"
    assert result["shared_configuration"]["compset_alias"].has_differences
    assert not result["shared_configuration"]["compset_alias"].varies


def test_missing_group_is_not_silently_treated_as_agreement():
    result = summarize_case_executions(
        [_run("a", "one"), _run("b", "two", compset_alias="   ")]
    )
    shared = result["shared_configuration"]["compset_alias"]
    assert shared.value is None
    assert shared.varies
    assert shared.incomplete
    assert not shared.has_differences
    assert (
        result["configuration_groups"][1].configuration["compset_alias"].source is None
    )


def test_configuration_run_end_fallback_and_input_order_independence():
    first = _run("a", "hash", run_end_date=_date(1))
    second = _run("b", "hash", run_start_date=_date(1), grid_alias="other")
    third = _run("c", "hash", run_start_date=_date(2), grid_alias="later")
    forward = summarize_case_executions([first, second, third])
    backward = summarize_case_executions([third, second, first])
    assert forward == backward
    assert (
        forward["configuration_groups"][0]
        .configuration["grid_alias"]
        .source.execution_id
        == "a"
    )


def test_shared_values_missing_groups_and_hashless_identity():
    result = summarize_case_executions(
        [
            _run("a", "one"),
            _run("b", "two", grid_alias=None),
            _run("c", None),
            _run("d", None, grid_alias="different"),
        ]
    )
    groups = result["configuration_groups"]
    assert len(groups) == 4
    hashless = [group for group in groups if group.case_hash is None]
    assert len({group.key for group in hashless}) == 2
    assert all(len(group.execution_ids) == 1 for group in hashless)
    shared = result["shared_configuration"]
    assert shared["compset_alias"].value == "compset"
    assert not shared["compset_alias"].varies
    assert shared["grid_alias"].value is None
    assert shared["grid_alias"].varies
    assert shared["grid_alias"].incomplete
    assert shared["git_tag"].value is None
    assert not shared["git_tag"].varies
    assert shared["git_tag"].incomplete


def test_coverage_unions_within_and_across_hashes_and_excludes_gaps():
    runs = [
        _run(
            "a",
            "one",
            simulation_start_date="1850-01-01",
            simulation_end_date="1860-01-01",
        ),
        _run(
            "b",
            "one",
            simulation_start_date="1855-01-01",
            simulation_end_date="1858-01-01",
        ),
        _run(
            "c",
            "two",
            simulation_start_date="1858-01-01",
            simulation_end_date="1860-01-01",
        ),
        _run(
            "d",
            None,
            simulation_start_date="1870-01-01",
            simulation_end_date="1880-01-01",
        ),
    ]
    result = summarize_case_executions(runs)
    assert result["simulation_coverage"].years == 20
    assert not result["simulation_coverage"].partial
    assert sorted(group.coverage.years for group in result["configuration_groups"]) == [
        2,
        10,
        10,
    ]


@pytest.mark.parametrize(
    ("start", "end", "years"),
    [
        ("0000-01-01", "0001-01-01", 1),
        ("0000-01-01", "0000-07-02", 0.5),
        ("2001-01-01", "2001-07-01", 181 / 365),
        ("2000-02-29", "2000-02-29", 0),
    ],
)
def test_coverage_model_years(start, end, years):
    coverage = simulation_coverage(
        [_run("a", "hash", simulation_start_date=start, simulation_end_date=end)]
    )
    assert coverage.years == pytest.approx(years)


def test_partial_and_unavailable_coverage():
    missing = _run("a", "hash", simulation_end_date=None)
    reversed_run = _run("b", "hash", simulation_end_date="1840-01-01")
    assert simulation_coverage([]).years is None
    assert not simulation_coverage([]).partial
    invalid_only = simulation_coverage([missing, reversed_run])
    assert invalid_only.years is None
    assert invalid_only.partial
    assert invalid_only.excluded_execution_count == 2
    partial = simulation_coverage([missing, reversed_run, _run("c", "hash")])
    assert partial.years == 10
    assert partial.partial


def test_latest_completed_uses_activity_not_input_order_or_audit_dates():
    runs = [
        _run("a", "hash", run_end_date=_date(1)),
        _run("b", "hash", run_start_date=_date(2)),
        _run("c", "hash", run_start_date=_date(2)),
        _run("d", "hash", run_end_date=_date(3), status=ExecutionStatus.FAILED),
        _run("z", "hash"),
    ]
    latest = summarize_case_executions(runs)["latest_execution"]
    assert latest.execution_id == "c"
    assert latest.run_start_date == _date(2)
    assert summarize_case_executions([runs[3]])["latest_execution"] is None
    assert summarize_case_executions([runs[4]])["latest_execution"].run_end_date is None


def test_empty_case_and_camel_case_serialization():
    aggregates = summarize_case_executions([])
    detail = CaseDetailOut(
        id=uuid4(), name="empty", created_at=_date(1), updated_at=_date(1), **aggregates
    ).model_dump(mode="json", by_alias=True)
    assert detail["configurationGroups"] == []
    assert detail["simulationCoverage"] == {
        "years": None,
        "partial": False,
        "excludedExecutionCount": 0,
    }
    assert detail["sharedConfiguration"]["compset_alias"]["value"] is None
    assert detail["latestExecution"] is None


def _run(execution_id, case_hash, **overrides):
    values = {
        "id": uuid4(),
        "execution_id": execution_id,
        "case_hash": case_hash,
        "compset_alias": "compset",
        "compset_long_name": "long compset",
        "grid_alias": "grid",
        "grid_long_name": "long grid",
        "status": ExecutionStatus.COMPLETED,
        "simulation_start_date": "1850-01-01",
        "simulation_end_date": "1860-01-01",
        **overrides,
    }

    return Execution(**values)


def _date(day):
    return datetime(2026, 1, day, tzinfo=timezone.utc)
