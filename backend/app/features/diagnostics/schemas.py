from typing import Literal
from uuid import UUID

from app.common.schemas.base import CamelOutBaseModel

Tool = Literal["e3sm_diags", "mpas_analysis"]


class DiagnosticsRunOut(CamelOutBaseModel):
    """One E3SM Diags or MPAS-Analysis run published for a case."""

    tool: Tool
    url: str
    subsection: str | None = None
    comparison: Literal["model_vs_obs", "model_vs_model"] | None = None
    start_year: int | None = None
    end_year: int | None = None
    ts_start_year: int | None = None
    ts_end_year: int | None = None


class DiagnosticsSourceOut(CamelOutBaseModel):
    """The runs found under one of the case's ``diagnostic`` links."""

    root_url: str
    label: str | None = None
    runs: list[DiagnosticsRunOut]
    truncated: bool = False
    error: str | None = None


class CaseDiagnosticsOut(CamelOutBaseModel):
    case_id: UUID
    case_name: str
    sources: list[DiagnosticsSourceOut]
