"""Read any supported run's catalog, choosing the reader from its URL."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.features.diagnostics import e3sm_diags, mpas_analysis
from app.features.diagnostics.archive import Fetcher, TTLCache, with_http_fetcher
from app.features.diagnostics.plots import Catalog


def read_catalog(url: str, fetch: Fetcher, label: str = "") -> Catalog:
    if not _is_parseable(url):
        return _unrecognized(url)
    if e3sm_diags.is_viewer_url(url):
        return e3sm_diags.read_catalog(url, fetch)
    if mpas_analysis.is_run_url(url):
        return mpas_analysis.read_catalog(url, fetch, label=label)
    return _unrecognized(url)


_cache: TTLCache[Catalog] = TTLCache()


def read_catalog_cached(url: str, label: str = "") -> Catalog:
    """``read_catalog`` over HTTP; complete, error-free reads are cached.

    A label can rename an MPAS case, so it is part of the cache key there.
    """
    if not _is_parseable(url):
        return _unrecognized(url)
    key = url.strip()
    if mpas_analysis.is_run_url(key) and label.startswith("!"):
        key = f"{key} {label}"
    if cached := _cache.get(key):
        return cached
    catalog = with_http_fetcher(lambda fetch: read_catalog(url, fetch, label))
    if catalog.error is None and not catalog.partial:
        _cache.put(key, catalog)
    return catalog


def _is_parseable(url: str) -> bool:
    # urlsplit raises on some malformed addresses, such as "https://[/viewer/".
    try:
        urlsplit(url.strip())
    except ValueError:
        return False
    return True


def _unrecognized(url: str) -> Catalog:
    return Catalog(url, None, url, error="unrecognized_url")
