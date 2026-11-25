"""Read pages from the public E3SM diagnostics web servers, safely.

Everything SimBoard knows about a diagnostics run comes from the HTML its tool
published: Apache directory listings, the E3SM Diags viewer, MPAS-Analysis
galleries. Those pages are read at request time, so this module keeps that
reading bounded and on known hosts:

* only URLs under ``settings.diagnostics_allowed_url_prefixes`` are fetched,
  and every redirect hop is checked again;
* each read has a request budget and a wall-clock deadline, and a body that
  trickles in or grows past a size cap is abandoned;
* "this page does not exist" is kept apart from "the server is down", so an
  outage is never cached as "this case has no diagnostics".

The fetch function is passed in everywhere, which keeps the tests offline.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar
from urllib.parse import unquote, urlsplit

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_USER_AGENT = "simboard-diagnostics/1.0"
_MAX_REDIRECTS = 3
# Outbound archive requests in flight across the whole process, however many
# users or runs are asking: keeps a burst from tying up workers or hammering
# the public servers.
_IN_FLIGHT = threading.BoundedSemaphore(settings.diagnostics_max_concurrent_requests)


class FetchOutcome(Enum):
    """Why a page has no body.

    ``ABSENT``: the server answered, and there is nothing there (404, or the
    403 Apache serves for a directory without an index). ``FAILED``: the
    server could not be reached or errored, which says nothing about the run.
    """

    ABSENT = "absent"
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    body: str | None = None
    outcome: FetchOutcome | None = None

    @property
    def failed(self) -> bool:
        return self.outcome is FetchOutcome.FAILED


ABSENT = FetchResult(outcome=FetchOutcome.ABSENT)
FAILED = FetchResult(outcome=FetchOutcome.FAILED)

# (url, seconds left in this read) -> page body, or why there is none.
Fetcher = Callable[[str, float], FetchResult]


def is_allowed_url(url: str) -> bool:
    """True when ``url`` is plain HTTPS under one of the allowed web roots.

    The path is checked segment by segment after decoding, so ``..`` (or
    ``%2e%2e``) cannot climb out of an allowed root on a server that
    normalizes paths. Credentials, ports, queries and fragments are refused.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or parts.username
        or port
        or parts.query
        or parts.fragment
    ):
        return False
    segments = unquote(parts.path).split("/")
    if any(segment in (".", "..") or "\\" in segment for segment in segments):
        return False

    path = parts.path.rstrip("/") + "/"
    for prefix in settings.diagnostics_allowed_url_prefixes_list:
        allowed = urlsplit(prefix)
        if parts.hostname == allowed.hostname and path.startswith(
            allowed.path.rstrip("/") + "/"
        ):
            return True
    return False


class Budget:
    """A request count and a deadline shared by every fetch in one read.

    Safe to share between threads, so one read can fetch pages in parallel.
    """

    def __init__(self, max_requests: int, deadline_seconds: float) -> None:
        self.max_requests = max_requests
        self.deadline = time.monotonic() + deadline_seconds
        self.requests_made = 0
        self.truncated = False
        self.failed = False
        self._lock = threading.Lock()

    @property
    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    @property
    def partial(self) -> bool:
        """Something was not read: the budget ran out or a fetch failed."""
        return self.truncated or self.failed

    def fetch(self, fetch: Fetcher, url: str) -> FetchResult | None:
        """Fetch ``url`` if budget remains; ``None`` once it is spent."""
        with self._lock:
            if self.requests_made >= self.max_requests or self.remaining <= 0:
                self.truncated = True
                return None
            self.requests_made += 1
        result = fetch(url, self.remaining)
        if result.failed:
            with self._lock:
                self.failed = True
        return result


def _classify(response: httpx.Response) -> FetchResult | None:
    """Outcome for a response that has no usable body, else ``None``."""
    if response.status_code in (403, 404):
        return ABSENT
    if response.status_code != 200:
        return FAILED
    if "html" not in response.headers.get("content-type", ""):
        return ABSENT
    return None


def _answer(response: httpx.Response, deadline: float) -> FetchResult:
    # A response that arrives after the deadline is a failed read, not an answer.
    if time.monotonic() >= deadline:
        return FAILED
    return _classify(response) or _read_body(response, deadline)


def _read_body(response: httpx.Response, deadline: float) -> FetchResult:
    # httpx's read timeout bounds the gap between chunks, not the response,
    # so a server trickling bytes would never time out on its own.
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if time.monotonic() >= deadline or size > settings.diagnostics_max_page_bytes:
            return FAILED
        chunks.append(chunk)
    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    return FetchResult(body=body)


def http_fetcher(client: httpx.Client) -> Fetcher:
    """A fetcher over ``client`` that enforces the rules in the module docstring."""

    def fetch(url: str, remaining: float) -> FetchResult:
        # Waiting for a slot spends the same budget as the read itself.
        deadline = time.monotonic() + remaining
        if not _IN_FLIGHT.acquire(timeout=max(0.0, remaining)):
            return FAILED
        try:
            return _fetch(url, deadline)
        finally:
            _IN_FLIGHT.release()

    def _fetch(url: str, deadline: float) -> FetchResult:
        target = url
        for _ in range(_MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return FAILED
            if not is_allowed_url(target):
                logger.warning(
                    "Diagnostics redirect left the allowed hosts: %s", target
                )
                return FAILED
            try:
                # httpx times each step (connect, read) separately; cap each step
                # at the time left. A late answer is FAILED in _answer.
                with client.stream(
                    "GET",
                    target,
                    headers={"User-Agent": _USER_AGENT},
                    follow_redirects=False,
                    timeout=min(
                        settings.diagnostics_request_timeout_seconds, remaining
                    ),
                ) as response:
                    # A late redirect fails at the top of the next hop.
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return FAILED
                        target = str(response.url.join(location))
                        continue
                    return _answer(response, deadline)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                # InvalidURL is not an HTTPError; a bad Location header raises it.
                logger.debug("Diagnostics fetch failed for %s: %s", url, exc)
                return FAILED
        return FAILED

    return fetch


def with_http_fetcher(read: Callable[[Fetcher], T]) -> T:
    """Run ``read`` with a fetcher backed by a short-lived HTTP client."""
    timeout = settings.diagnostics_request_timeout_seconds
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        return read(http_fetcher(client))


class SingleFlight(Generic[T]):
    """Run one read per key at a time; concurrent callers share its result.

    A shared link or a reload starts several requests for the same uncached
    run at once. Without this, each would read the archive separately.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[str, Future[T]] = {}

    def run(self, key: str, read: Callable[[], T]) -> T:
        with self._lock:
            running = self._running.get(key)
            leader = running is None
            if running is None:
                running = self._running[key] = Future()
        if not leader:
            return running.result()
        try:
            result = read()
        except BaseException as exc:
            running.set_exception(exc)
            raise
        else:
            running.set_result(result)
            return result
        finally:
            with self._lock:
                del self._running[key]


class TTLCache(Generic[T]):
    """A small thread-safe, size-capped, in-process cache with expiry."""

    def __init__(
        self,
        ttl_seconds: float = settings.diagnostics_cache_ttl_seconds,
        max_entries: int = settings.diagnostics_cache_max_entries,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, T]] = {}  # oldest first

    def get(self, key: str) -> T | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry[0] < time.monotonic():
                del self._entries[key]
                return None
            return entry[1]

    def put(self, key: str, value: T, ttl_seconds: float | None = None) -> None:
        now = time.monotonic()
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._entries.pop(key, None)
            for stale in [k for k, (exp, _) in self._entries.items() if exp < now]:
                del self._entries[stale]
            while len(self._entries) >= self._max_entries:
                del self._entries[next(iter(self._entries))]
            self._entries[key] = (now + ttl, value)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
