"""Case-detail aggregates over all executions, independent of row pagination."""

import calendar
from datetime import datetime, timezone

from app.common.model_dates import normalize_model_date
from app.features.catalog.enums import ExecutionStatus
from app.features.catalog.models import Execution
from app.features.catalog.schemas import (
    CaseHashConfigurationOut,
    ConfigurationFieldOut,
    ConfigurationObservationOut,
    LatestExecutionSummaryOut,
    SharedConfigurationFieldOut,
    SimulationCoverageOut,
)

CONFIGURATION_FIELDS = (
    "compset_alias",
    "compset_long_name",
    "grid_alias",
    "grid_long_name",
    "git_tag",
    "git_commit_hash",
)


def summarize_case_executions(executions: list[Execution]) -> dict:
    """Return case-wide and per-hash aggregates from the full relationship."""
    grouped: dict[str, list[Execution]] = {}
    for execution in executions:
        key = execution.case_hash or f"missing:{execution.id}"
        grouped.setdefault(key, []).append(execution)

    groups = []
    for key, members in sorted(grouped.items()):
        ordered = sorted(members, key=_configuration_order)
        groups.append(
            CaseHashConfigurationOut(
                key=key,
                case_hash=ordered[0].case_hash or None,
                execution_ids=[execution.execution_id for execution in ordered],
                configuration={
                    field: _summarize_field(ordered, field)
                    for field in CONFIGURATION_FIELDS
                },
                coverage=simulation_coverage(members),
            )
        )

    return {
        "configuration_groups": groups,
        "shared_configuration": {
            field: _shared_field(groups, field) for field in CONFIGURATION_FIELDS
        },
        "simulation_coverage": simulation_coverage(executions),
        "latest_execution": _latest_execution(executions),
    }


def simulation_coverage(executions: list[Execution]) -> SimulationCoverageOut:
    """Merge [start, end) intervals; gaps and excluded intervals add no time.

    A date's fractional year is its zero-based day divided by that year's
    length. This supports year zero and makes January-to-January years exact.
    """
    intervals: list[tuple[str, str]] = []
    excluded = 0
    for execution in executions:
        try:
            start = normalize_model_date(execution.simulation_start_date)
            end = normalize_model_date(execution.simulation_end_date)
            if end < start:
                raise ValueError("Reversed simulation interval")
        except ValueError:
            excluded += 1
            continue
        intervals.append((start, end))

    merged: list[tuple[str, str]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    years = sum(
        _fractional_year(end) - _fractional_year(start) for start, end in merged
    )

    return SimulationCoverageOut(
        years=round(years, 8) if intervals else None,
        partial=excluded > 0,
        excluded_execution_count=excluded,
    )


def _configuration_order(execution: Execution) -> tuple:
    run_date = execution.run_start_date or execution.run_end_date

    return (
        run_date is None,
        _timestamp(run_date),
        execution.execution_id,
        str(execution.id),
    )


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return float("-inf")

    return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()


def _summarize_field(executions: list[Execution], field: str) -> ConfigurationFieldOut:
    result = ConfigurationFieldOut()
    for execution in executions:
        value = getattr(execution, field)
        if not value:
            result.missing_execution_ids.append(execution.execution_id)
            continue
        observation = ConfigurationObservationOut(
            value=value,
            execution_uuid=execution.id,
            execution_id=execution.execution_id,
            run_date=execution.run_start_date or execution.run_end_date,
        )
        if result.source is None:
            result.source = observation
        elif value != result.source.value:
            result.differences.append(observation)

    return result


def _shared_field(
    groups: list[CaseHashConfigurationOut], field: str
) -> SharedConfigurationFieldOut:
    values = {
        source.value if (source := group.configuration[field].source) else None
        for group in groups
    }

    return SharedConfigurationFieldOut(
        value=next(iter(values)) if len(values) == 1 else None,
        varies=len(values) > 1,
        incomplete=any(
            group.configuration[field].missing_execution_ids for group in groups
        ),
    )


def _latest_execution(executions: list[Execution]) -> LatestExecutionSummaryOut | None:
    completed = [run for run in executions if run.status == ExecutionStatus.COMPLETED]
    if not completed:
        return None
    # Match the catalog list's completed-run ordering, including undated ties.
    latest = max(
        completed,
        key=lambda run: (
            _timestamp(run.run_end_date or run.run_start_date),
            _timestamp(run.run_end_date),
            _timestamp(run.run_start_date),
            run.execution_id,
        ),
    )

    return LatestExecutionSummaryOut(
        execution_id=latest.execution_id,
        status=latest.status,
        run_start_date=latest.run_start_date,
        run_end_date=latest.run_end_date,
    )


def _fractional_year(value: str) -> float:
    year, month, day = map(int, value.split("-"))
    day_of_year = (
        sum(calendar.monthrange(year, m)[1] for m in range(1, month)) + day - 1
    )

    return year + day_of_year / (366 if calendar.isleap(year) else 365)
