from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.common.dependencies import get_database_session
from app.core.logger import _setup_custom_logger
from app.features.assistant.schemas import SimulationSummaryResponse
from app.features.assistant.service import build_simulation_summary
from app.features.simulation.models import Simulation
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/simulations", tags=["Simulation Assistant"])
logger = _setup_custom_logger(__name__)


@router.post(
    "/{sim_id}/summary",
    response_model=SimulationSummaryResponse,
    responses={
        200: {"description": "Deterministic summary generated successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Simulation not found."},
    },
)
def summarize_simulation(
    sim_id: UUID,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
) -> SimulationSummaryResponse:
    """Generate a deterministic read-only summary for one simulation."""

    start = perf_counter()
    trace_id = uuid4()

    simulation = (
        db.query(Simulation)
        .options(
            joinedload(Simulation.case),
            joinedload(Simulation.machine),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .filter(Simulation.id == sim_id)
        .one_or_none()
    )

    if simulation is None:
        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "simulation_summary trace_id=%s simulation_id=%s user_id=%s success=false "
            "status=not_found latency_ms=%.2f citation_count=0 caveat_count=0",
            trace_id,
            sim_id,
            user.id,
            duration_ms,
        )
        raise HTTPException(status_code=404, detail="Simulation not found")

    summary = build_simulation_summary(simulation)
    summary = summary.model_copy(update={"trace_id": trace_id})

    duration_ms = (perf_counter() - start) * 1000
    logger.info(
        "simulation_summary trace_id=%s simulation_id=%s user_id=%s success=true "
        "latency_ms=%.2f citation_count=%d caveat_count=%d",
        trace_id,
        simulation.id,
        user.id,
        duration_ms,
        len(summary.citations),
        len(summary.caveats),
    )

    return summary
