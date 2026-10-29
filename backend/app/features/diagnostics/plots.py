"""The plot catalog every diagnostics tool is read into."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tool = Literal["e3sm_diags", "mpas_analysis"]


@dataclass(frozen=True)
class Plot:
    """One published image.

    ``key`` names the same diagnostic in every run, with run-specific text
    (case names, years, model-vs-model reference prefixes) removed, so plots
    line up across runs. ``group`` gathers the seasons and regions of one
    variable into a single row; ``title`` and ``reference`` label that row.
    """

    key: str
    path: str
    group: str
    title: str
    reference: str
    season: str | None = None
    region: str | None = None
    # A few E3SM Diags images are single figures rather than the usual
    # test/reference/difference composite.
    single_panel: bool = False


@dataclass(frozen=True)
class PlotSet:
    name: str
    title: str
    plots: tuple[Plot, ...]


@dataclass(frozen=True)
class Catalog:
    """Everything one run published that SimBoard can show."""

    url: str
    tool: Tool | None
    image_base_url: str
    sets: tuple[PlotSet, ...] = ()
    truncated: bool = False
    error: str | None = None
