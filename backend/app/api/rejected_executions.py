"""Protected, read-only listing of currently rejected executions."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.features.ingestion.api import (
    _require_ingestion_state_access,
    _resolve_machine_ids,
)
from app.features.ingestion.enums import ExecutionDiscoveryOutcome
from app.features.ingestion.models import ExecutionDiscoveryResult
from app.features.ingestion.schemas import (
    RejectedExecutionRead,
    RejectedExecutionsResponse,
)
from app.features.machine.models import Machine
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])

REJECTED_EXECUTIONS_MAX = 200
REJECTED_OUTCOMES = (
    ExecutionDiscoveryOutcome.REJECTED_INCOMPLETE,
    ExecutionDiscoveryOutcome.REJECTED_INVALID,
)


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
    },
)
def get_rejected_executions(
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
    machine_name: str | None = None,
    site_name: str | None = None,
) -> RejectedExecutionsResponse:
    """Return up to 200 currently rejected executions and the full count."""
    _require_ingestion_state_access(user, action="read rejected executions")
    machine_ids = _resolve_machine_ids(db, machine_name, site_name)

    query = (
        select(ExecutionDiscoveryResult, Machine.name)
        .join(Machine, ExecutionDiscoveryResult.machine_id == Machine.id)
        .where(ExecutionDiscoveryResult.outcome.in_(REJECTED_OUTCOMES))
    )
    if machine_ids is not None:
        query = query.where(ExecutionDiscoveryResult.machine_id.in_(machine_ids))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(
            Machine.name,
            ExecutionDiscoveryResult.case_identity,
            ExecutionDiscoveryResult.execution_id,
        ).limit(REJECTED_EXECUTIONS_MAX)
    )
    executions = [
        RejectedExecutionRead(
            machine_name=result_machine_name,
            case_identity=result.case_identity,
            execution_id=result.execution_id,
            outcome=result.outcome,
            errors=result.errors or [],
        )
        for result, result_machine_name in rows
    ]

    return RejectedExecutionsResponse(executions=executions, total=total)
