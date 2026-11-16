"""Protected, read-only reporting of newly persisted executions."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.features.ingestion.api import (
    _require_ingestion_state_access,
    _resolve_machine_ids,
    _validate_report_date_range,
)
from app.features.ingestion.schemas import IngestionSummaryResponse
from app.features.ingestion.summary import summarize_ingestions
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/ingestions", tags=["Ingestions"])


@router.get(
    "/summary",
    response_model=IngestionSummaryResponse,
    responses={
        403: {
            "description": "Only administrators and service accounts may read summaries."
        },
        404: {"description": "Machine or site not found."},
        422: {"description": "Invalid dates or a range exceeding 90 days."},
    },
)
def get_ingestion_summary(
    start_date: date,
    end_date: date,
    db: Annotated[Session, Depends(get_database_session)],
    user: Annotated[User, Depends(current_active_user)],
    machine_name: str | None = None,
    site_name: str | None = None,
) -> IngestionSummaryResponse:
    """Count executions created in [start_date, end_date), using UTC days."""
    _require_ingestion_state_access(user, action="read summaries")
    _validate_report_date_range(start_date, end_date)
    machine_ids = _resolve_machine_ids(db, machine_name, site_name)

    return summarize_ingestions(db, start_date, end_date, machine_ids)
