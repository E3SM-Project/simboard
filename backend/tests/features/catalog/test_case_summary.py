"""Case configuration and coverage policies, without relying on query order."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.features.catalog.case_summary import (
    simulation_coverage,
    simulation_duration,
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


def test_duration_counts_overlaps_and_hash_totals_independently():
    runs = [
        _run("a", "one", extra={"simulation_calendar": "NO_LEAP"}),
        _run("b", "one", extra={"simulation_calendar": "365_day"}),
        _run("c", "two", extra={"simulation_calendar": "noleap"}),
    ]
    result = summarize_case_executions(runs)
    assert result["simulated_duration"].days == 30 * 365
    assert result["simulated_duration"].years == 30
    assert result["simulation_coverage"].years == 10
    assert [
        group.simulated_duration.years for group in result["configuration_groups"]
    ] == [20, 10]
    assert summarize_case_executions(list(reversed(runs))) == result


@pytest.mark.parametrize(
    ("model_calendar", "start", "end", "days", "months"),
    [
        ("GREGORIAN", "0000-01-01", "0001-01-01", 366, 12),
        ("proleptic_gregorian", "2000-02-01", "2000-03-01", 29, 1),
        ("noleap", "2000-02-01", "2000-03-01", 28, 1),
        ("360_day", "2000-02-01", "2000-03-01", 30, 1),
        ("noleap", "2001-01-01", "2001-01-08", 7, 7 / 31),
        ("gregorian", "2000-02-29", "2000-02-29", 0, 0),
    ],
)
def test_duration_model_calendars(model_calendar, start, end, days, months):
    result = simulation_duration(
        [
            _run(
                "a",
                "hash",
                simulation_start_date=start,
                simulation_end_date=end,
                extra={"simulation_calendar": model_calendar},
            )
        ]
    )
    assert result.days == days
    assert result.months == pytest.approx(months)
    assert result.years == pytest.approx(months / 12)
    assert not result.partial


def test_duration_unknown_invalid_and_unfinished_runs():
    valid = _run("valid", "hash", extra={"simulation_calendar": "gregorian"})
    runs = [
        _run("unsupported", "hash", extra={"simulation_calendar": "julian"}),
        _run("missing", "hash", simulation_end_date=None, extra=valid.extra),
        _run("reversed", "hash", simulation_end_date="1849-01-01", extra=valid.extra),
        _run(
            "invalid-noleap",
            "hash",
            simulation_start_date="2000-02-29",
            simulation_end_date="2000-03-01",
            extra={"simulation_calendar": "noleap"},
        ),
        _run("planned", "hash", status=ExecutionStatus.RUNNING, extra=valid.extra),
    ]
    excluded = simulation_duration(runs)
    assert excluded.days is None
    assert excluded.excluded_execution_count == len(runs)
    assert excluded.partial
    partial = simulation_duration([valid, *runs])
    assert partial.years == 10
    assert partial.excluded_execution_count == len(runs)
    assert (
        simulation_duration(
            [_run("failed", "hash", status=ExecutionStatus.FAILED)]
        ).days
        is None
    )
    assert simulation_duration([]).days is None
    assert not simulation_duration([]).partial


def test_duration_flags_legacy_gregorian_storage_assumption():
    result = simulation_duration([_run("legacy", "hash")])
    assert result.years == 10
    assert result.calendar_assumed
    assert result.calendars == ["gregorian"]
    explicit = simulation_duration(
        [_run("explicit", "hash", extra={"simulation_calendar": "gregorian"})]
    )
    assert not explicit.calendar_assumed


def test_duration_mixed_calendars_exposes_days_not_equivalent_years():
    result = simulation_duration(
        [
            _run("a", "hash", extra={"simulation_calendar": "gregorian"}),
            _run("b", "hash", extra={"simulation_calendar": "noleap"}),
        ]
    )
    assert result.days == 7302
    assert result.months is None
    assert result.years is None
    assert result.calendars == ["gregorian", "noleap"]
    assert not result.partial


def test_source_code_path_and_model_hash_have_configuration_provenance():
    result = summarize_case_executions(
        [
            _run(
                "a",
                "hash",
                git_commit_hash="model-hash",
                extra={"source_code_path": "/model/source"},
            )
        ]
    )
    configuration = result["configuration_groups"][0].configuration
    assert configuration["source_code_path"].source.value == "/model/source"
    assert configuration["git_commit_hash"].source.value == "model-hash"


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
    assert detail["simulatedDuration"] == {
        "days": None,
        "months": None,
        "years": None,
        "calendars": [],
        "calendarAssumed": False,
        "partial": False,
        "excludedExecutionCount": 0,
    }


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
