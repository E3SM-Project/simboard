import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.common.schemas.base import CamelOutBaseModel

PACE_BASE_URL = "https://pace.ornl.gov"
PACE_LOOKUP_TIMEOUT_SECONDS = 5.0

router = APIRouter(prefix="/pace", tags=["PACE"])


class PaceResolutionOut(CamelOutBaseModel):
    execution_id: str
    experiment_id: str | None


@router.get(
    "/resolve",
    response_model=PaceResolutionOut,
    responses={
        200: {"description": "PACE resolution result."},
        422: {"description": "Validation error."},
    },
)
def resolve_pace_execution(
    execution_id: Annotated[
        str,
        Query(
            ...,
            description="Simulation execution ID to resolve to a PACE experiment ID.",
        ),
    ],
) -> PaceResolutionOut:
    normalized_execution_id = _normalize_execution_id(execution_id)

    return PaceResolutionOut(
        execution_id=normalized_execution_id,
        experiment_id=_resolve_experiment_id(normalized_execution_id),
    )


def _normalize_execution_id(execution_id: str) -> str:
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id:
        raise HTTPException(status_code=422, detail="execution_id must not be blank")

    return normalized_execution_id


def _resolve_experiment_id(execution_id: str) -> str | None:
    request = urllib.request.Request(
        _build_pace_lookup_url(execution_id),
        headers={"Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(
            request, timeout=PACE_LOOKUP_TIMEOUT_SECONDS
        ) as response:
            if response.status != 200:
                return None

            response_body = response.read().decode("utf-8")
    except (
        TimeoutError,
        UnicodeDecodeError,
        urllib.error.HTTPError,
        urllib.error.URLError,
    ):
        return None

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return None

    return _extract_experiment_id(payload)


def _build_pace_lookup_url(execution_id: str) -> str:
    encoded_execution_id = urllib.parse.quote(execution_id, safe="")
    return f"{PACE_BASE_URL}/ajax/specificSearch/lid:{encoded_execution_id}/expid"


def _extract_experiment_id(payload: Any) -> str | None:
    if not isinstance(payload, list) or not payload:
        return None

    first_item = payload[0]
    if not isinstance(first_item, dict):
        return None

    experiment_id = first_item.get("expid")
    if not isinstance(experiment_id, str):
        return None

    normalized_experiment_id = experiment_id.strip()
    return normalized_experiment_id or None
