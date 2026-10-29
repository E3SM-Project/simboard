"""Read the plots an E3SM Diags run published, from its own viewer pages.

A run's ``viewer/index.html`` links one page per plot set, and each set page
names its images in ``data-preview`` attributes::

    viewer/lat_lon/index.html  ->  lat_lon/GPCP_v3.2/GPCP_v3.2-PRECT-ANN-global.png

Image names follow ``<reference>-<VARIABLE>[-<level>]-<SEASON>-<region>.png``.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import unquote, urljoin, urlsplit

from app.core.config import settings
from app.features.diagnostics.archive import Budget, Fetcher, is_allowed_url
from app.features.diagnostics.plots import Catalog, Plot, PlotSet

SEASONS = ("ANN", "DJF", "MAM", "JJA", "SON")

# Sets with no comparable images: ``table`` is text, ``taylor`` and ``cmip6``
# are single summaries, and ``tropical_subseasonal`` publishes an archive.
UNSUPPORTED_SETS = frozenset({"table", "taylor", "cmip6", "tropical_subseasonal"})

# Each E3SM Diags image stacks the test run, the reference and their
# difference in one 1275 px wide PNG. These windows onto each panel, as
# (width, height, top, left) in image pixels, follow IICE's stylesheet.
IMAGE_WIDTH = 1275


class Panel(NamedTuple):
    width: int
    height: int
    top: int
    left: int


_STANDARD = {
    "test": Panel(1050, 505, 60, 165),
    "ref": Panel(1050, 505, 555, 165),
    "diff": Panel(1050, 495, 1055, 165),
}
PANELS: dict[str, dict[str, Panel]] = {
    "lat_lon": _STANDARD,
    "zonal_mean_2d": _STANDARD,
    "zonal_mean_2d_stratosphere": _STANDARD,
    "meridional_mean_2d": _STANDARD,
    "polar": {
        "test": Panel(680, 595, 35, 300),
        "ref": Panel(680, 535, 580, 300),
        "diff": Panel(680, 535, 1085, 300),
    },
    "cosp_histogram": {
        "test": Panel(1075, 545, 60, 90),
        "ref": Panel(1075, 490, 590, 90),
        "diff": Panel(1075, 495, 1060, 90),
    },
    "annual_cycle_zonal_mean": {
        "test": Panel(1050, 505, 60, 150),
        "ref": Panel(1050, 505, 555, 150),
        "diff": Panel(1050, 495, 1040, 150),
    },
    "enso_diags": {
        "test": Panel(1050, 525, 40, 165),
        "ref": Panel(1050, 465, 565, 165),
        "diff": Panel(1050, 505, 1058, 165),
    },
    "zonal_mean_xy": {
        "test": Panel(1120, 760, 60, 50),
        "diff": Panel(1120, 760, 820, 50),
    },
    "diurnal_cycle": {
        "test": Panel(1080, 510, 105, 150),
        "ref": Panel(1080, 510, 615, 150),
    },
}

_SET_LINK_RE = re.compile(r"^([a-z0-9_]+)/index\.html$")
_MODEL_VS_MODEL = frozenset({"model_vs_model", "model-vs-model"})


def is_viewer_url(url: str) -> bool:
    return urlsplit(normalize_url(url)).path.endswith("/viewer/")


def normalize_url(url: str) -> str:
    """The run's ``.../viewer/`` URL with one trailing slash."""
    return url.strip().removesuffix("index.html").rstrip("/") + "/"


def parse_filename(filename: str) -> tuple[str, str | None, str | None]:
    """``(variable, season, region)`` from an image name.

    Fields are read from the right because references contain hyphens
    (``CERES-EBAF-TOA-v4.1``). A pressure level joins its variable
    (``U-850``). Names without a season keep their stem as the variable.
    """
    stem = filename.removesuffix(".png")
    fields = stem.split("-")
    if len(fields) >= 3 and fields[-2:] == ["Annual", "Cycle"]:
        return fields[-3], None, None
    if len(fields) >= 3 and fields[-2] in SEASONS:
        variable = fields[-3]
        if variable.isdigit() and len(fields) >= 4:
            variable = f"{fields[-4]}-{variable}"
        return variable, fields[-2], fields[-1]
    return stem, None, None


def plot_from_path(set_name: str, path: str) -> Plot | None:
    """A ``Plot`` for ``<set>/<reference dir>/<file>.png``, or ``None``."""
    parts = path.split("/")
    if len(parts) != 3 or parts[0] != set_name:
        return None
    _, directory, filename = parts
    variable, season, region = parse_filename(filename)

    if season:
        identity = f"{variable}-{season}-{region}"
    elif filename.endswith("-Annual-Cycle.png"):
        identity = f"{variable}-Annual-Cycle"
    else:
        identity = filename

    # Model-vs-model images all live in one directory and are prefixed with
    # the reference case, which differs between runs: keep it out of the key.
    reference = directory
    if directory in _MODEL_VS_MODEL and (marker := filename.find(f"-{variable}-")) > 0:
        reference = filename[:marker]

    return Plot(
        key=f"{set_name}/{directory}/{identity}",
        path=path,
        group=f"{set_name}/{directory}/{variable}",
        title=variable,
        reference=reference,
        season=season,
        region=region,
        single_panel=filename.startswith("feedback-"),
    )


class _ViewerIndexParser(HTMLParser):
    """``(set name, title)`` for each set linked from ``viewer/index.html``."""

    def __init__(self) -> None:
        super().__init__()
        self.sets: dict[str, str] = {}
        self._set: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        match = _SET_LINK_RE.match(dict(attrs).get("href") or "")
        if tag == "a" and match:
            self._set, self._text = match[1], []

    def handle_data(self, data: str) -> None:
        if self._set:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._set:
            title = " ".join("".join(self._text).split()) or self._set
            self.sets.setdefault(self._set, title)
            self._set = None


class _PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.previews: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        preview = dict(attrs).get("data-preview") or ""
        if tag == "a" and preview.lower().endswith(".png"):
            self.previews.append(preview)


def parse_viewer_index(html: str) -> dict[str, str]:
    parser = _ViewerIndexParser()
    parser.feed(html)
    return parser.sets


def parse_set_page(html: str, set_name: str) -> list[Plot]:
    """The set's plots in page order, once each."""
    parser = _PreviewParser()
    parser.feed(html)
    plots: dict[str, Plot] = {}
    for preview in parser.previews:
        plot = plot_from_path(set_name, unquote(preview).lstrip("./"))
        if plot:
            plots.setdefault(plot.key, plot)
    return list(plots.values())


def read_catalog(
    url: str,
    fetch: Fetcher,
    *,
    max_requests: int | None = None,
    deadline_seconds: float | None = None,
) -> Catalog:
    """Read every comparable plot set from the run at ``url``."""
    viewer = normalize_url(url)
    image_base = urljoin(viewer, "../")
    if not is_allowed_url(viewer):
        return Catalog(viewer, "e3sm_diags", image_base, error="url_not_allowed")

    budget = Budget(
        max_requests or settings.diagnostics_max_requests,
        deadline_seconds or settings.diagnostics_catalog_deadline_seconds,
    )
    index = budget.fetch(fetch, urljoin(viewer, "index.html"))
    if index is None or index.body is None:
        return Catalog(viewer, "e3sm_diags", image_base, error="catalog_unavailable")

    sets = []
    for name, title in parse_viewer_index(index.body).items():
        if name in UNSUPPORTED_SETS:
            continue
        page = budget.fetch(fetch, urljoin(viewer, f"{name}/index.html"))
        if page is None:
            break
        if page.body and (plots := parse_set_page(page.body, name)):
            sets.append(PlotSet(name, title, tuple(plots)))

    return Catalog(viewer, "e3sm_diags", image_base, tuple(sets), budget.truncated)
