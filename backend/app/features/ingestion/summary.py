"""Aggregate current execution records by their UTC creation day."""

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import distinct, func, select, tuple_
from sqlalchemy.orm import Session

from app.features.catalog.models import Case, Execution
from app.features.ingestion.schemas import (
    IngestionSummaryDayTotals,
    IngestionSummaryMachineTotals,
    IngestionSummaryResponse,
    IngestionSummaryRow,
    IngestionSummaryTotals,
)
from app.features.machine.models import Machine


def summarize_ingestions(
    db: Session,
    start_date: date,
    end_date: date,
    machine_id: UUID | None = None,
) -> IngestionSummaryResponse:
    """Read case rows and SQL-computed totals from one database snapshot."""
    day = func.date(func.timezone("UTC", Execution.created_at))
    statement = (
        select(
            day.label("day"),
            Machine.name.label("machine"),
            Case.id.label("case_id"),
            Case.name.label("case_name"),
            Case.hpc_username,
            func.count().label("new_executions"),
            func.count(distinct(Case.id)).label("distinct_cases"),
        )
        .select_from(Execution)
        .join(Case, Execution.case_id == Case.id)
        .join(Machine, Case.machine_id == Machine.id)
        .where(
            Execution.created_at
            >= datetime.combine(start_date, time.min, timezone.utc),
            Execution.created_at < datetime.combine(end_date, time.min, timezone.utc),
        )
        .group_by(
            func.grouping_sets(
                tuple_(day, Machine.name, Case.id, Case.name, Case.hpc_username),
                tuple_(day, Machine.name),
                tuple_(day),
                tuple_(),
            )
        )
        .order_by(
            day.asc().nulls_last(),
            Machine.name.asc().nulls_last(),
            Case.name.asc().nulls_last(),
            Case.hpc_username.asc().nulls_last(),
            Case.id.asc().nulls_last(),
        )
    )
    if machine_id is not None:
        statement = statement.where(Case.machine_id == machine_id)

    response = IngestionSummaryResponse()
    # Grouped-away keys are NULL; all corresponding source columns are non-null.
    for row in db.execute(statement).mappings():
        if row["day"] is None:
            response.totals = IngestionSummaryTotals.model_validate(row)
        elif row["machine"] is None:
            response.daily_totals.append(IngestionSummaryDayTotals.model_validate(row))
        elif row["case_id"] is None:
            response.daily_machine_totals.append(
                IngestionSummaryMachineTotals.model_validate(row)
            )
        else:
            response.rows.append(IngestionSummaryRow.model_validate(row))

    return response
