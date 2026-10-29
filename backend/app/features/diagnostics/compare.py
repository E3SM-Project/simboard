"""Line up the plots several runs published, for side-by-side viewing.

Only plots every run published are offered, so a comparison never shows a
plot for one run and a gap for another; how many were left out is reported.
Plots are matched by ``Plot.key``, never by filename, because filenames carry
case names, years and model-vs-model reference cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.diagnostics import e3sm_diags
from app.features.diagnostics.plots import Catalog, Plot, PlotSet

SEASON_ORDER = ("ANN", "DJF", "MAM", "JJA", "SON", "JFM", "JAS")


@dataclass(frozen=True)
class SharedSet:
    name: str
    title: str
    plots: tuple[Plot, ...]  # as the first run published them
    missing: int


@dataclass(frozen=True)
class Group:
    """A row in the variable list: one variable's seasons and regions."""

    id: str
    title: str
    reference: str
    plots: tuple[Plot, ...]


def shared_sets(catalogs: list[Catalog]) -> list[SharedSet]:
    """Sets and plots every readable run has, in the first run's order.

    A run that read cleanly but published nothing comparable still counts,
    and so leaves nothing shared.
    """
    usable = [c for c in catalogs if c.error is None]
    if not usable:
        return []
    first, *rest = usable
    shared = []
    for plot_set in first.sets:
        others = [_keys(c, plot_set.name) for c in rest]
        plots = tuple(
            p for p in plot_set.plots if all(p.key in keys for keys in others)
        )
        if plots:
            missing = len(plot_set.plots) - len(plots)
            shared.append(SharedSet(plot_set.name, plot_set.title, plots, missing))
    return shared


def group_plots(plots: tuple[Plot, ...]) -> list[Group]:
    groups: dict[str, list[Plot]] = {}
    for plot in plots:
        groups.setdefault(plot.group, []).append(plot)
    return [
        Group(id, members[0].title, members[0].reference, tuple(_ordered(members)))
        for id, members in groups.items()
    ]


def find_plot(catalog: Catalog, set_name: str, key: str) -> Plot | None:
    plot_set = _set(catalog, set_name)
    return next((p for p in plot_set.plots if p.key == key), None) if plot_set else None


def panels(tool: str | None, set_name: str) -> dict[str, e3sm_diags.Panel]:
    """Panel windows for a set's composite images; empty to show them whole."""
    return e3sm_diags.PANELS.get(set_name, {}) if tool == "e3sm_diags" else {}


def _set(catalog: Catalog, name: str) -> PlotSet | None:
    return next((s for s in catalog.sets if s.name == name), None)


def _keys(catalog: Catalog, set_name: str) -> set[str]:
    plot_set = _set(catalog, set_name)
    return {p.key for p in plot_set.plots} if plot_set else set()


def _ordered(plots: list[Plot]) -> list[Plot]:
    def season_rank(plot: Plot) -> int:
        season = plot.season or ""
        return (
            SEASON_ORDER.index(season) if season in SEASON_ORDER else len(SEASON_ORDER)
        )

    # Stable: regions keep the order the run published them in.
    return sorted(plots, key=season_rank)
