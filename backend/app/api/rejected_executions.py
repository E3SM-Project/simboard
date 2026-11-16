"""Protected, read-only summary of currently rejected executions."""

from datetime import date, datetime, time, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import Subquery, distinct, func, select, tuple_
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.features.ingestion.api import (
    _require_ingestion_state_access,
    _resolve_machine_ids,
    _validate_report_date_range,
)
from app.features.ingestion.enums import ExecutionDiscoveryOutcome
from app.features.ingestion.models import ExecutionDiscoveryResult
from app.features.ingestion.schemas import (
    RejectedExecutionExample,
    RejectedExecutionGroup,
    RejectedExecutionsResponse,
)
from app.features.machine.models import Machine
from app.features.site.models import Site
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])

REJECTED_OUTCOMES = (
    ExecutionDiscoveryOutcome.REJECTED_INCOMPLETE,
    ExecutionDiscoveryOutcome.REJECTED_INVALID,
)
EXAMPLE_COLUMNS = ("machine_name", "case_identity", "execution_id", "message")


@router.get(
    "/rejected-executions",
    response_model=RejectedExecutionsResponse,
    responses={
        403: {
            "description": (
                "Only administrators and service accounts may read rejected executions."
            )
        },
        404: {"description": "Machine or site not found."},
        422: {"description": "Invalid dates or a range exceeding 90 days."},
    },
)
def get_rejected_executions(
    start_date: date,
    end_date: date,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
    machine_name: str | None = None,
    site_name: str | None = None,
) -> RejectedExecutionsResponse:
    """Group current rejections by site, outcome, and first error.

    ``new_in_range`` counts rejections first detected in [start_date, end_date),
    using UTC days. Groups with the most new rejections come first.
    """
    _require_ingestion_state_access(user, action="read rejected executions")
    _validate_report_date_range(start_date, end_date)

    rejections = _rejections_subquery(_resolve_machine_ids(db, machine_name, site_name))
    keys = (
        rejections.c.site_name,
        rejections.c.outcome,
        rejections.c.code,
        rejections.c.target,
    )
    is_new = (
        rejections.c.created_at >= datetime.combine(start_date, time.min, timezone.utc)
    ) & (rejections.c.created_at < datetime.combine(end_date, time.min, timezone.utc))
    is_example = rejections.c.example_rank == 1
    new_in_range = func.count().filter(is_new)
    executions = func.count()

    # One statement, so counts and examples come from the same snapshot.
    rows = db.execute(
        select(
            *keys,
            executions.label("executions"),
            # Case identities are unique per machine, not per site.
            func.count(
                distinct(tuple_(rejections.c.machine_id, rejections.c.case_identity))
            ).label("cases"),
            new_in_range.label("new_in_range"),
            func.max(rejections.c.created_at).label("latest_detected_at"),
            *(
                func.max(rejections.c[name]).filter(is_example).label(name)
                for name in EXAMPLE_COLUMNS
            ),
        )
        .group_by(*keys)
        .order_by(new_in_range.desc(), executions.desc(), *keys)
    ).mappings()
    groups = [
        RejectedExecutionGroup(
            **row, example=RejectedExecutionExample.model_validate(row)
        )
        for row in rows
    ]

    return RejectedExecutionsResponse(
        groups=groups,
        total=sum(group.executions for group in groups),
        new_in_range=sum(group.new_in_range for group in groups),
    )


def _rejections_subquery(machine_ids: list[UUID] | None) -> Subquery:
    """Select current rejections with their site, first error, and example rank.

    Rank 1 is each group's newest rejection.
    """
    first_error = ExecutionDiscoveryResult.errors[0]
    code = first_error["code"].astext
    target = func.coalesce(first_error["file_spec"].astext, first_error["field"].astext)
    query = (
        select(
            Site.name.label("site_name"),
            Machine.name.label("machine_name"),
            ExecutionDiscoveryResult.machine_id,
            ExecutionDiscoveryResult.outcome,
            code.label("code"),
            target.label("target"),
            first_error["message"].astext.label("message"),
            ExecutionDiscoveryResult.case_identity,
            ExecutionDiscoveryResult.execution_id,
            ExecutionDiscoveryResult.created_at,
            func.row_number()
            .over(
                partition_by=(
                    Site.name,
                    ExecutionDiscoveryResult.outcome,
                    code,
                    target,
                ),
                order_by=(
                    ExecutionDiscoveryResult.created_at.desc(),
                    Machine.name,
                    ExecutionDiscoveryResult.case_identity,
                    ExecutionDiscoveryResult.execution_id,
                ),
            )
            .label("example_rank"),
        )
        .join(Machine, ExecutionDiscoveryResult.machine_id == Machine.id)
        .join(Site, Machine.site_id == Site.id)
        .where(ExecutionDiscoveryResult.outcome.in_(REJECTED_OUTCOMES))
    )
    if machine_ids is not None:
        query = query.where(ExecutionDiscoveryResult.machine_id.in_(machine_ids))

    return query.subquery()
