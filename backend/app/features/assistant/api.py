from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.database_async import get_async_session
from app.core.logger import _setup_custom_logger
from app.features.assistant.orchestrator import generate_simulation_summary
from app.features.assistant.schemas import SimulationSummaryResponse
from app.features.simulation.models import Case, Simulation
from app.features.user.manager import optional_current_user
from app.features.user.models import User

router = APIRouter(prefix="/simulations", tags=["Simulation Assistant"])
logger = _setup_custom_logger(__name__)


@router.post(
    "/{sim_id}/summary",
    response_model=SimulationSummaryResponse,
    responses={
        200: {"description": "Simulation summary generated successfully."},
        401: {"description": "Unauthorized."},
        404: {"description": "Simulation not found."},
    },
)
async def summarize_simulation(
    sim_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(optional_current_user),
) -> SimulationSummaryResponse:
    """Generate a metadata-grounded read-only summary for one simulation."""

    start = perf_counter()
    trace_id = uuid4()

    stmt = (
        select(Simulation)
        .options(
            joinedload(Simulation.case).joinedload(Case.machine),
            joinedload(Simulation.case).selectinload(Case.links),
            selectinload(Simulation.artifacts),
            selectinload(Simulation.links),
        )
        .where(Simulation.id == sim_id)
    )
    result = await db.execute(stmt)
    simulation = result.scalars().unique().one_or_none()

    if simulation is None:
        duration_ms = (perf_counter() - start) * 1000
        user_id = user.id if user is not None else "null"
        logger.info(
            "simulation_summary trace_id=%s simulation_id=%s user_id=%s success=false "
            "status=not_found llm_success=false fallback_used=false latency_ms=%.2f llm_latency_ms=%.2f generation_mode=%s "
            "generation_provider=%s generation_model=%s fallback_reason=%s "
            "citation_count=0 caveat_count=0",
            trace_id,
            sim_id,
            user_id,
            duration_ms,
            0.0,
            "deterministic",
            "null",
            "null",
            "simulation_not_found",
        )
        raise HTTPException(status_code=404, detail="Simulation not found")

    generation = await generate_simulation_summary(
        simulation, allow_llm=user is not None
    )
    llm_success = generation.summary.generation_mode == "llm"
    fallback_used = (
        not llm_success
        and generation.fallback_reason is not None
        and generation.fallback_reason != "llm_disabled"
    )
    summary = generation.summary.model_copy(
        update={
            "trace_id": trace_id,
            "fallback_used": fallback_used,
        }
    )

    duration_ms = (perf_counter() - start) * 1000
    user_id = user.id if user is not None else "null"
    logger.info(
        "simulation_summary trace_id=%s simulation_id=%s user_id=%s success=true "
        "llm_success=%s fallback_used=%s latency_ms=%.2f llm_latency_ms=%.2f generation_mode=%s "
        "generation_provider=%s generation_model=%s fallback_reason=%s citation_count=%d caveat_count=%d",
        trace_id,
        simulation.id,
        user_id,
        str(llm_success).lower(),
        str(fallback_used).lower(),
        duration_ms,
        generation.llm_latency_ms,
        summary.generation_mode,
        generation.attempted_provider or "null",
        generation.attempted_model or "null",
        generation.fallback_reason or "null",
        len(summary.citations),
        len(summary.caveats),
    )

    return summary
