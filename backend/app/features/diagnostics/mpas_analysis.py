"""Read the plots an MPAS-Analysis run published, from its gallery pages.

A run publishes ``ocean/index.html`` and ``sea_ice/index.html``. Each figure
there names its full-size PNG, a caption, and a short description that is a
season (``JFM``) or a region (``Eastern Ross Sea Shelf``); headings give the
section and observation set above it.

Image names embed the case name and years, so both are stripped to match the
same plot across runs. The case name comes from the URL. Older runs use
layouts it cannot be read from; for those, as in IICE, a run label starting
with ``!`` supplies it (``!my.case``) or the years (``!yrs1-10``).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from app.core.config import settings
from app.features.diagnostics.archive import Budget, Fetcher, is_allowed_url
from app.features.diagnostics.plots import Catalog, Plot, PlotSet

COMPONENTS = {"ocean": "Ocean", "sea_ice": "Sea ice"}

# zppy: <case>/mpas_analysis/ts_Y1-Y2_climo_Y1-Y2/
_ZPPY_RE = re.compile(
    r"/(?P<case>[^/]+)/mpas_analysis/(?:[^/]+/)*ts_\d+-\d+_climo_\d+-\d+/$"
)
# Older: <case>_yrsY1-Y2/html/, <case>/html/ and <case>/yrsY1-Y2/
_LEGACY_RES = (
    re.compile(r"/(?P<case>[^/]+?)_?yrs\d+-\d+/html/$"),
    re.compile(r"/(?P<case>[^/]+)/html/$"),
    re.compile(r"/(?P<case>[^/]+)/yrs\d+-\d+/$"),
)
_YEARS_RE = re.compile(r"_years\d+-\d+")
_SEASON_RE = re.compile(r"^(?:ANN|[JFMASOND]{2,3})$")


def normalize_url(url: str) -> str:
    return url.strip().removesuffix("index.html").rstrip("/") + "/"


def is_run_url(url: str) -> bool:
    path = urlsplit(normalize_url(url)).path
    return "/mpas_analysis/" in path or any(r.search(path) for r in _LEGACY_RES)


def case_name(url: str, label: str = "") -> str | None:
    """The case name in ``url``'s image names, or from a ``!case`` label."""
    override = label.strip()
    if override.startswith("!"):
        token = override[1:].split(" ", 1)[0]
        if token and not re.fullmatch(r"yrs\d+-\d+", token):
            return token
    path = urlsplit(normalize_url(url)).path
    for pattern in (_ZPPY_RE, *_LEGACY_RES):
        if match := pattern.search(path):
            return match["case"]
    return None


class _GalleryParser(HTMLParser):
    """``(href, section, caption, description)`` for each gallery figure."""

    def __init__(self) -> None:
        super().__init__()
        self.figures: list[tuple[str, str, str, str]] = []
        self._section = ""
        self._capture: str | None = None  # "heading", "caption" or "desc"
        self._text: list[str] = []
        self._figure: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in ("h2", "h3", "h4"):
            self._start("heading")
        elif tag == "figure":
            self._figure = {}
        elif self._figure is None:
            return
        elif tag == "a" and (values.get("href") or "").lower().endswith(".png"):
            self._figure.setdefault("href", values["href"] or "")
        elif tag == "figcaption":
            self._start("caption")
        elif tag == "div" and "desc-small" in (values.get("class") or ""):
            self._start("desc")

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = " ".join("".join(self._text).split())
        if tag in ("h2", "h3", "h4") and self._capture == "heading":
            self._section, self._capture = text, None
        elif (
            tag in ("figcaption", "div") and self._capture and self._figure is not None
        ):
            self._figure[self._capture], self._capture = text, None
        elif tag == "figure" and self._figure is not None:
            figure, self._figure = self._figure, None
            if href := figure.get("href"):
                self.figures.append(
                    (
                        href,
                        self._section,
                        figure.get("caption", ""),
                        figure.get("desc", ""),
                    )
                )

    def _start(self, what: str) -> None:
        self._capture, self._text = what, []


def split_description(desc: str) -> tuple[str | None, str | None]:
    """``(season, region)`` from a figure's short description.

    It reads ``JFM``, ``Eastern Ross Sea Shelf``, ``JAS z=-600 m`` or
    ``Eastern Ross Sea Shelf ANN``; whatever is not the season is the region
    (a basin, transect or depth).
    """
    words = desc.split()
    if words and _SEASON_RE.match(words[0]):
        return words[0], " ".join(words[1:]) or None
    if len(words) > 1 and _SEASON_RE.match(words[-1]):
        return words[-1], " ".join(words[:-1])
    return None, desc or None


def _title(caption: str, season: str | None, region: str | None) -> str:
    """The caption with its season and region taken out, to name a row."""
    title = caption.replace("$\\degree$", "°")
    if region:
        head, sep, _ = title.partition(f" in {region}")
        title = head if sep else title.replace(region, "")
    if season:
        title = re.sub(rf"^{season} | {season}$", "", title.strip())
    title = " ".join(title.split()).strip(" .")
    # Removing a leading region can leave a fragment ("of El Nino ..."); a
    # plot like that is its own row.
    return title if title[:1].isupper() else caption


def parse_gallery(html: str, component: str, case: str) -> list[Plot]:
    """Plots on one Ocean or Sea ice gallery page, once each, in page order.

    Plots whose captions differ only by season and region share a ``group``,
    so a field's seasons and depths are choices on one row.
    """
    parser = _GalleryParser()
    parser.feed(html)

    plots: dict[str, Plot] = {}
    variants: set[tuple[str, str | None, str | None]] = set()
    for href, section, caption, desc in parser.figures:
        path = f"{component}/{unquote(href).lstrip('./')}"
        stem = path.rsplit("/", 1)[-1].removesuffix(".png")
        stem = _YEARS_RE.sub("", stem.replace(f"_{case}", ""))
        key = f"{component}/{section}/{stem}"
        if key in plots:
            continue

        season, region = split_description(desc)
        title = _title(caption, season, region) if caption else stem
        group = f"{component}/{section}/{title}"
        if (group, season, region) in variants:
            group = key  # same caption, season and region: keep it apart
        variants.add((group, season, region))

        plots[key] = Plot(
            key=key,
            path=path,
            group=group,
            title=title,
            reference=section,
            season=season,
            region=region,
        )
    return list(plots.values())


def read_catalog(
    url: str,
    fetch: Fetcher,
    *,
    label: str = "",
    max_requests: int | None = None,
    deadline_seconds: float | None = None,
) -> Catalog:
    """Read the Ocean and Sea ice galleries of the run at ``url``."""
    run = normalize_url(url)
    if not is_allowed_url(run):
        return Catalog(run, "mpas_analysis", run, error="url_not_allowed")
    case = case_name(run, label)
    if not case:
        return Catalog(run, "mpas_analysis", run, error="case_name_unknown")

    budget = Budget(
        max_requests or settings.diagnostics_max_requests,
        deadline_seconds or settings.diagnostics_catalog_deadline_seconds,
    )
    sets = []
    for component, title in COMPONENTS.items():
        page = budget.fetch(fetch, urljoin(run, f"{component}/index.html"))
        if page is None:
            break
        if page.body and (plots := parse_gallery(page.body, component, case)):
            sets.append(PlotSet(component, title, tuple(plots)))

    error = None if sets or budget.partial else "catalog_unavailable"
    return Catalog(run, "mpas_analysis", run, tuple(sets), budget.partial, error)
