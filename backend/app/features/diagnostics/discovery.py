"""List the diagnostics runs published under a case's archive root.

A case stores one ``diagnostic`` link: the root of its zppy output. Under it,
zppy writes many individual runs in a fixed layout::

    <root>/e3sm_diags/<subsection>/<model_vs_obs|model_vs_model>_<Y1>-<Y2>/viewer/
    <root>/mpas_analysis/ts_<Y1>-<Y2>_climo_<Y1>-<Y2>/

The archive servers publish Apache directory listings, so the runs are found
by reading at most two levels of them. Only these names are followed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from app.core.config import settings
from app.features.diagnostics.archive import (
    Budget,
    Fetcher,
    TTLCache,
    is_allowed_url,
    with_http_fetcher,
)

Tool = Literal["e3sm_diags", "mpas_analysis"]
Comparison = Literal["model_vs_obs", "model_vs_model"]

_E3SM_RUN_RE = re.compile(
    r"^(?P<comparison>model_vs_obs|model_vs_model)_(?P<start>\d{4,})-(?P<end>\d{4,})$"
)
_MPAS_RUN_RE = re.compile(
    r"^ts_(?P<ts_start>\d{4,})-(?P<ts_end>\d{4,})"
    r"_climo_(?P<start>\d{4,})-(?P<end>\d{4,})$"
)
# Listed names are joined into request URLs, so accept only what zppy writes.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class DiagnosticsRun:
    tool: Tool
    url: str
    subsection: str | None = None
    comparison: Comparison | None = None
    start_year: int | None = None
    end_year: int | None = None
    ts_start_year: int | None = None
    ts_end_year: int | None = None


@dataclass(frozen=True)
class Discovery:
    root_url: str
    runs: tuple[DiagnosticsRun, ...]
    partial: bool = False
    error: str | None = None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.append(href)


def parse_directory_index(html: str) -> list[str]:
    """Child directory names in an Apache listing, without trailing slashes.

    Parent, absolute and sort links, files, nested paths and anything that is
    not a plain zppy-style name are dropped.
    """
    parser = _LinkParser()
    parser.feed(html)
    names = (href[:-1] for href in parser.hrefs if href.endswith("/"))
    return [name for name in names if _SAFE_NAME_RE.match(name)]


def _dir(base: str, *names: str) -> str:
    return "/".join([base.rstrip("/"), *names]) + "/"


def _listing(budget: Budget, fetch: Fetcher, url: str) -> list[str]:
    result = budget.fetch(fetch, url)
    if result is None or result.body is None:
        return []
    return sorted(parse_directory_index(result.body))


def _e3sm_runs(root: str, fetch: Fetcher, budget: Budget) -> list[DiagnosticsRun]:
    base = _dir(root, "e3sm_diags")
    runs = []
    for subsection in _listing(budget, fetch, base):
        for name in _listing(budget, fetch, _dir(base, subsection)):
            match = _E3SM_RUN_RE.match(name)
            if not match:
                continue
            comparison: Comparison = (
                "model_vs_model"
                if match["comparison"] == "model_vs_model"
                else "model_vs_obs"
            )
            runs.append(
                DiagnosticsRun(
                    tool="e3sm_diags",
                    url=_dir(base, subsection, name, "viewer"),
                    subsection=subsection,
                    comparison=comparison,
                    start_year=int(match["start"]),
                    end_year=int(match["end"]),
                )
            )
    return runs


def _mpas_runs(root: str, fetch: Fetcher, budget: Budget) -> list[DiagnosticsRun]:
    base = _dir(root, "mpas_analysis")
    return [
        DiagnosticsRun(
            tool="mpas_analysis",
            url=_dir(base, name),
            start_year=int(match["start"]),
            end_year=int(match["end"]),
            ts_start_year=int(match["ts_start"]),
            ts_end_year=int(match["ts_end"]),
        )
        for name in _listing(budget, fetch, base)
        if (match := _MPAS_RUN_RE.match(name))
    ]


def discover_runs(
    root_url: str,
    fetch: Fetcher,
    *,
    max_requests: int | None = None,
    deadline_seconds: float | None = None,
) -> Discovery:
    """Every E3SM Diags and MPAS-Analysis run published under ``root_url``.

    If the budget runs out or a listing fails, the runs found are kept and the
    result is marked ``partial``. An unreachable archive is an ``error`` only
    when it leaves nothing, so one bad subdirectory does not hide the others.
    """
    if not is_allowed_url(root_url):
        return Discovery(root_url, (), error="url_not_allowed")

    budget = Budget(
        max_requests or settings.diagnostics_max_requests,
        deadline_seconds or settings.diagnostics_discovery_deadline_seconds,
    )
    runs = _e3sm_runs(root_url, fetch, budget) + _mpas_runs(root_url, fetch, budget)
    error = "archive_unavailable" if budget.failed and not runs else None
    return Discovery(root_url, tuple(runs), budget.partial, error)


_cache: TTLCache[Discovery] = TTLCache()


def discover_runs_cached(root_url: str) -> Discovery:
    """``discover_runs`` over HTTP; complete, error-free results are cached."""
    if cached := _cache.get(root_url):
        return cached
    result = with_http_fetcher(lambda fetch: discover_runs(root_url, fetch))
    if result.error is None and not result.partial:
        _cache.put(root_url, result)
    return result
