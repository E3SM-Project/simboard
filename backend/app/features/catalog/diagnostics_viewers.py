"""Discover IICE-compatible diagnostics viewers under a published archive root.

SimBoard stores one ``diagnostic`` link per case: the root of that case's
published zppy output (for example
``.../diagnostics_archive/production/v3.LR.historical_0101``). IICE, the
Interface for Inter-Comparison of E3SM diagnostics, needs something more
specific: the ``viewer/`` directory of an individual e3sm_diags run, or the
timeseries/climatology directory of an individual mpas-analysis run. A single
case commonly publishes a dozen or more of these.

zppy lays those out predictably::

    <root>/e3sm_diags/<subsection>/<model_vs_obs|model_vs_model>_<Y1>-<Y2>/viewer/
    <root>/mpas_analysis/ts_<Y1>-<Y2>_climo_<Y1>-<Y2>/

Both reviewed archive web servers serve Apache directory indexes, so the
layout can be read at request time with a small, bounded crawl. This module
owns that crawl and the parsing of what it finds. It is deliberately
conservative: it only follows the two directory names above, only two levels
deep, only on reviewed archive hosts, and only up to a fixed request budget.

The fetch function is injected so tests run entirely offline.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Public types
# ----------------------------------------------------------------------------

DiagnosticsTool = Literal["e3sm_diags", "mpas_analysis"]
ComparisonKind = Literal["model_vs_obs", "model_vs_model"]

# zppy directory conventions. Year fields are zero-padded model years or
# calendar years; both are four or more digits.
_E3SM_DIAGS_RUN_RE = re.compile(
    r"^(?P<comparison>model_vs_obs|model_vs_model)_(?P<start>\d{4,})-(?P<end>\d{4,})$"
)
_MPAS_ANALYSIS_RUN_RE = re.compile(
    r"^ts_(?P<ts_start>\d{4,})-(?P<ts_end>\d{4,})_climo_(?P<climo_start>\d{4,})-(?P<climo_end>\d{4,})$"
)
# Model-vs-model subsections carry a short reference tag after ``_mvm_`` in
# zppy's naming, e.g. ``atm_monthly_180x360_aave_mvm_PI100``. It is a hint,
# not the reference case name IICE needs; see ``reference_hint`` below.
_MVM_TAG_RE = re.compile(r"_mvm(?:_(?P<tag>.+))?$")
# Directory names are joined straight into a URL, so keep them to the plain
# characters zppy actually produces. This also keeps control characters and
# percent escapes out of the request, which httpx rejects with InvalidURL.
_SAFE_INDEX_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class DiagnosticsViewer:
    """One IICE-addressable diagnostics output.

    Attributes
    ----------
    tool
        Which package produced the output.
    url
        For e3sm_diags, the ``viewer/`` directory with a trailing slash. For
        mpas_analysis, the ``ts_..._climo_...`` directory with a trailing
        slash. In both cases this is exactly what IICE expects in ``urlN``.
    subsection
        The zppy subsection directory name (e3sm_diags only).
    comparison
        ``model_vs_obs`` or ``model_vs_model`` (e3sm_diags only).
    start_year, end_year
        The climatology period for e3sm_diags, or the climatology period for
        mpas_analysis.
    ts_start_year, ts_end_year
        The timeseries period (mpas_analysis only).
    reference_hint
        For model_vs_model runs, the tag zppy appended to the subsection
        name. IICE needs the full reference *case name* in a ``!ref`` label
        prefix to resolve model_vs_model image filenames; this hint lets the
        UI pre-fill something sensible that the user can correct.
    """

    tool: DiagnosticsTool
    url: str
    subsection: str | None = None
    comparison: ComparisonKind | None = None
    start_year: int | None = None
    end_year: int | None = None
    ts_start_year: int | None = None
    ts_end_year: int | None = None
    reference_hint: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    """Everything discovered under one archive root, plus how it went."""

    root_url: str
    viewers: tuple[DiagnosticsViewer, ...]
    requests_made: int
    truncated: bool
    error: str | None = None


class FetchOutcome(Enum):
    """Why a directory listing is unavailable.

    ``ABSENT`` means the archive answered and there is no index here: a
    missing directory, or the ``403`` served for a directory without one.
    Discovery treats that as a fact about the case. ``FAILED`` means the
    archive could not be reached or errored, which says nothing about the
    case and must not be mistaken for "no runs".
    """

    ABSENT = "absent"
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    """A directory index body, or the reason there is not one."""

    body: str | None = None
    outcome: FetchOutcome | None = None

    @property
    def failed(self) -> bool:
        return self.outcome is FetchOutcome.FAILED


# A fetcher takes a URL and a remaining-time budget, and returns the body or
# the reason it is unavailable. Keeping it this narrow is what lets the tests
# stay offline.
Fetcher = Callable[[str, float], FetchResult]


# ----------------------------------------------------------------------------
# Directory index parsing
# ----------------------------------------------------------------------------


class _IndexLinkParser(HTMLParser):
    """Collect ``href`` values from an Apache-style directory index."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)


def parse_directory_index(html: str) -> list[str]:
    """Return the child directory names listed in an Apache directory index.

    Only relative, single-segment entries ending in ``/`` are returned, so
    parent links, absolute links, query-sorted column headers, and files are
    all excluded. Names must also look like the plain directory names zppy
    writes; anything else is skipped rather than joined into a request URL.
    Names are returned without the trailing slash.
    """
    parser = _IndexLinkParser()
    try:
        parser.feed(html)
    except Exception:  # pragma: no cover - HTMLParser is lenient; belt and braces
        return []

    names: list[str] = []
    for href in parser.hrefs:
        if not href.endswith("/") or href.startswith(("/", "?", "#", "..")):
            continue
        if "://" in href:
            continue
        name = href[:-1]
        if not _SAFE_INDEX_NAME_RE.match(name):
            continue
        names.append(name)
    return names


# ----------------------------------------------------------------------------
# Host allowlist
# ----------------------------------------------------------------------------


def is_allowed_archive_url(url: str) -> bool:
    """True when ``url`` sits under one of the reviewed archive base URLs.

    The crawl follows server-provided links, so it must never be pointed at an
    arbitrary host. Prefix matching on the configured base URLs keeps it on the
    two reviewed diagnostics archives.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        return False
    normalized = url.rstrip("/") + "/"
    for prefix in settings.diagnostics_viewer_allowed_url_prefixes_list:
        base = prefix + "/"
        if normalized.startswith(base):
            return True
    return False


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------


def _join_dir(base: str, *segments: str) -> str:
    url = base.rstrip("/") + "/"
    for segment in segments:
        url = urljoin(url, segment.strip("/") + "/")
    return url


def _e3sm_diags_viewers(
    root_url: str, fetch: Fetcher, budget: _Budget
) -> Iterable[DiagnosticsViewer]:
    e3sm_dir = _join_dir(root_url, "e3sm_diags")
    subsections = budget.listing(fetch, e3sm_dir)
    for subsection in subsections:
        runs = budget.listing(fetch, _join_dir(e3sm_dir, subsection))
        for run in runs:
            match = _E3SM_DIAGS_RUN_RE.match(run)
            if not match:
                continue
            comparison: ComparisonKind = (
                "model_vs_model"
                if match.group("comparison") == "model_vs_model"
                else "model_vs_obs"
            )
            hint = None
            if comparison == "model_vs_model":
                tag_match = _MVM_TAG_RE.search(subsection)
                if tag_match:
                    hint = tag_match.group("tag")
            yield DiagnosticsViewer(
                tool="e3sm_diags",
                url=_join_dir(e3sm_dir, subsection, run, "viewer"),
                subsection=subsection,
                comparison=comparison,
                start_year=int(match.group("start")),
                end_year=int(match.group("end")),
                reference_hint=hint,
            )


def _mpas_analysis_viewers(
    root_url: str, fetch: Fetcher, budget: _Budget
) -> Iterable[DiagnosticsViewer]:
    mpas_dir = _join_dir(root_url, "mpas_analysis")
    for run in budget.listing(fetch, mpas_dir):
        match = _MPAS_ANALYSIS_RUN_RE.match(run)
        if not match:
            continue
        yield DiagnosticsViewer(
            tool="mpas_analysis",
            url=_join_dir(mpas_dir, run),
            start_year=int(match.group("climo_start")),
            end_year=int(match.group("climo_end")),
            ts_start_year=int(match.group("ts_start")),
            ts_end_year=int(match.group("ts_end")),
        )


class _Budget:
    """Stop listing once either the request count or the wall-clock budget is spent.

    The per-request timeout bounds one slow response; the deadline bounds the
    whole crawl, so a sluggish archive can never hold a case page hostage.
    Whatever was found before the budget ran out is still returned, flagged
    ``truncated``.
    """

    def __init__(self, max_requests: int, deadline_seconds: float) -> None:
        self.max_requests = max_requests
        self.deadline = time.monotonic() + deadline_seconds
        self.requests_made = 0
        self.truncated = False
        self.failed = False

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def spend(self) -> bool:
        """Charge one request, or report that the budget is exhausted."""
        if self.requests_made >= self.max_requests or self.remaining_seconds <= 0:
            self.truncated = True
            return False
        self.requests_made += 1
        return True

    def listing(self, fetch: Fetcher, url: str) -> list[str]:
        if not self.spend():
            return []
        result = fetch(url, self.remaining_seconds)
        if result.failed:
            self.failed = True
        if result.body is None:
            return []
        return sorted(parse_directory_index(result.body))


def discover_diagnostics_viewers(
    root_url: str,
    fetch: Fetcher,
    *,
    max_requests: int | None = None,
    deadline_seconds: float | None = None,
) -> DiscoveryResult:
    """Crawl one archive root and return the IICE-addressable viewers under it.

    Parameters
    ----------
    root_url
        The case's published diagnostics root, as stored on its ``diagnostic``
        external link.
    fetch
        Given a URL and the seconds left in the crawl, returns the directory
        index body or the reason it is unavailable.
    max_requests
        Upper bound on index fetches for this root. Defaults to the configured
        ``diagnostics_viewer_discovery_max_requests``.
    deadline_seconds
        Upper bound on total wall-clock time for this root. Defaults to the
        configured ``diagnostics_viewer_discovery_deadline_seconds``.

    Notes
    -----
    Roots outside the reviewed archive hosts are refused without any network
    access and reported through ``DiscoveryResult.error``.
    """
    if not is_allowed_archive_url(root_url):
        return DiscoveryResult(
            root_url=root_url,
            viewers=(),
            requests_made=0,
            truncated=False,
            error="root_not_in_reviewed_archive",
        )

    budget = _Budget(
        max_requests or settings.diagnostics_viewer_discovery_max_requests,
        deadline_seconds or settings.diagnostics_viewer_discovery_deadline_seconds,
    )
    viewers: list[DiagnosticsViewer] = []
    viewers.extend(_e3sm_diags_viewers(root_url, fetch, budget))
    viewers.extend(_mpas_analysis_viewers(root_url, fetch, budget))

    # A reachable archive with no runs is a fact about the case; an archive we
    # could not reach is not. Only report the second as an error, and only
    # when it left us with nothing, so one flaky subdirectory among many good
    # ones still yields a useful listing.
    error = "archive_unavailable" if budget.failed and not viewers else None

    return DiscoveryResult(
        root_url=root_url,
        viewers=tuple(viewers),
        requests_made=budget.requests_made,
        truncated=budget.truncated,
        error=error,
    )


# ----------------------------------------------------------------------------
# HTTP fetcher and cache used by the API
# ----------------------------------------------------------------------------

_USER_AGENT = "simboard-diagnostics-viewer-discovery/1.0"
_MAX_REDIRECTS = 3


def _read_index_body(
    response: httpx.Response, deadline: float, max_bytes: int, url: str
) -> FetchResult:
    """Stream one index body, abandoning it on the deadline or the size cap."""
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        if time.monotonic() >= deadline:
            logger.debug("Diagnostics index timed out mid-body: %s", url)
            return FetchResult(outcome=FetchOutcome.FAILED)
        size += len(chunk)
        if size > max_bytes:
            logger.debug("Diagnostics index exceeded size cap: %s", url)
            return FetchResult(outcome=FetchOutcome.FAILED)
        chunks.append(chunk)

    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    return FetchResult(body=body)


def _classify_index_response(response: httpx.Response) -> FetchResult | None:
    """Map a non-redirect response to an outcome, or ``None`` to read the body.

    ``403`` is what the archive serves for a directory without an index, and
    ``404`` for one that does not exist. Both mean "no listing here" rather
    than "the archive is broken".
    """
    if response.status_code in (403, 404):
        return FetchResult(outcome=FetchOutcome.ABSENT)
    if response.status_code != 200:
        return FetchResult(outcome=FetchOutcome.FAILED)
    if "html" not in response.headers.get("content-type", ""):
        return FetchResult(outcome=FetchOutcome.ABSENT)

    return None


def http_directory_fetcher(client: httpx.Client) -> Fetcher:
    """Build a fetcher over ``client`` that returns index bodies or a reason.

    Three things this guards, none of which the client options cover on their
    own:

    * **Total time.** ``httpx``'s read timeout bounds the gap between chunks,
      not the whole response, so an archive trickling data stays under it
      forever. The body is streamed and abandoned once the crawl's remaining
      time runs out.
    * **Body size.** A directory index is kilobytes. Reading stops past
      ``diagnostics_viewer_max_index_bytes`` rather than buffering whatever
      arrives.
    * **Redirects.** Following them automatically would let an allowed archive
      point the backend at an unreviewed or internal host. Each hop is
      validated against the allowlist and charged to the redirect limit.

    Timeouts, transport errors and ``5xx`` are ``FAILED``, which keeps an
    unreachable archive from being cached as "no runs".
    """

    def fetch(url: str, remaining_seconds: float) -> FetchResult:
        deadline = time.monotonic() + remaining_seconds
        max_bytes = settings.diagnostics_viewer_max_index_bytes
        target = url

        for _hop in range(_MAX_REDIRECTS + 1):
            if time.monotonic() >= deadline:
                return FetchResult(outcome=FetchOutcome.FAILED)
            if not is_allowed_archive_url(target):
                logger.warning(
                    "Diagnostics index redirect left the reviewed archives: %s", target
                )
                return FetchResult(outcome=FetchOutcome.FAILED)

            try:
                with client.stream(
                    "GET",
                    target,
                    headers={"User-Agent": _USER_AGENT},
                    follow_redirects=False,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return FetchResult(outcome=FetchOutcome.FAILED)
                        target = str(response.url.join(location))
                        continue

                    classified = _classify_index_response(response)
                    if classified is not None:
                        return classified

                    return _read_index_body(response, deadline, max_bytes, url)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                # InvalidURL is not an HTTPError, and a malformed Location
                # header reaches us through the same path as a transport fault.
                logger.debug("Diagnostics index fetch failed for %s: %s", url, exc)
                return FetchResult(outcome=FetchOutcome.FAILED)

        logger.warning("Diagnostics index exceeded redirect limit: %s", url)

        return FetchResult(outcome=FetchOutcome.FAILED)

    return fetch


class DiscoveryCache:
    """Small in-process TTL cache keyed by archive root URL.

    Discovery is a handful of outbound requests to a shared web server, so
    repeated page views of the same case must not repeat it. Process-local is
    enough for now; the cache is a performance aid, not a source of truth.
    """

    def __init__(self, ttl_seconds: float, max_entries: int = 200) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # Insertion-ordered, so the oldest entry is always first.
        self._entries: dict[str, tuple[float, DiscoveryResult]] = {}

    def get(self, root_url: str) -> DiscoveryResult | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(root_url)
            if entry is None:
                return None
            expires_at, result = entry
            if expires_at < now:
                del self._entries[root_url]
                return None
            return result

    def put(self, root_url: str, result: DiscoveryResult) -> None:
        now = time.monotonic()
        with self._lock:
            self._entries.pop(root_url, None)
            expired = [
                key
                for key, (expires_at, _) in self._entries.items()
                if expires_at < now
            ]
            for key in expired:
                del self._entries[key]
            while len(self._entries) >= self._max_entries:
                del self._entries[next(iter(self._entries))]
            self._entries[root_url] = (now + self._ttl, result)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


discovery_cache = DiscoveryCache(
    settings.diagnostics_viewer_cache_ttl_seconds,
    settings.diagnostics_viewer_cache_max_entries,
)


def discover_with_cache(root_url: str) -> DiscoveryResult:
    """Discover viewers for ``root_url`` over HTTP, serving repeats from cache.

    Results with an ``error`` are not cached, so a transient failure on the
    archive side is retried on the next request.
    """
    cached = discovery_cache.get(root_url)
    if cached is not None:
        return cached

    timeout = settings.diagnostics_viewer_discovery_timeout_seconds
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        result = discover_diagnostics_viewers(root_url, http_directory_fetcher(client))

    if result.error is None:
        discovery_cache.put(root_url, result)
    return result
