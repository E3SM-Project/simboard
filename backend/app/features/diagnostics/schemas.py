from typing import Literal
from uuid import UUID

from pydantic import Field

from app.common.schemas.base import CamelInBaseModel, CamelOutBaseModel

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


class CompareRunIn(CamelInBaseModel):
    url: str = Field(min_length=1)
    label: str = ""


class CompareRequest(CamelInBaseModel):
    runs: list[CompareRunIn] = Field(min_length=1, max_length=12)
    set: str | None = Field(
        None, description="Plot set to detail; the first if omitted."
    )


class CompareRunOut(CamelOutBaseModel):
    url: str
    label: str
    tool: Tool | None = None
    image_base_url: str
    truncated: bool = False
    error: str | None = None


class PanelOut(CamelOutBaseModel):
    """A window onto one panel of a composite image, in image pixels."""

    width: int
    height: int
    top: int
    left: int


class ComparedPlotOut(CamelOutBaseModel):
    key: str
    season: str | None = None
    region: str | None = None
    single_panel: bool = False
    # One entry per requested run, in order; null where it could not be read.
    paths: list[str | None] = Field(
        description="Image path in each run, relative to its imageBaseUrl."
    )
    references: list[str | None] = Field(
        description="What each run compared against: an observation set, or "
        "the reference case of a model-vs-model run."
    )


class GroupOut(CamelOutBaseModel):
    id: str
    title: str
    reference: str
    plots: list[ComparedPlotOut]


class SetSummaryOut(CamelOutBaseModel):
    name: str
    title: str
    plot_count: int
    missing: int


class SetDetailOut(SetSummaryOut):
    image_width: int | None = None
    panels: dict[str, PanelOut] = {}
    groups: list[GroupOut]


class CompareOut(CamelOutBaseModel):
    runs: list[CompareRunOut]
    sets: list[SetSummaryOut]
    set: SetDetailOut | None = None
