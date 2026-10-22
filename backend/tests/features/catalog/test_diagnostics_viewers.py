"""Tests for IICE diagnostics viewer discovery.

Every test runs offline. Directory indexes are served from an in-memory
fake archive shaped like the real zppy output on the LCRC diagnostics archive,
and the HTTP fetcher is exercised through an ``httpx.MockTransport``.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.core.config import settings
from app.features.catalog.diagnostics_viewers import (
    DiscoveryCache,
    DiscoveryResult,
    FetchOutcome,
    FetchResult,
    discover_diagnostics_viewers,
    discover_with_cache,
    discovery_cache,
    http_directory_fetcher,
    is_allowed_archive_url,
    parse_directory_index,
)
from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.models import Case, ExternalLink
from app.features.machine.models import Machine

LCRC_ROOT = (
    "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive"
    "/production/v3.LR/v3.LR.historical_0101"
)


def _apache_index(title: str, entries: list[str]) -> str:
    """Render an Apache ``mod_autoindex`` page, including its noise."""
    rows = "\n".join(
        f'<tr><td><a href="{name}">{name}</a></td><td>2026-09-16 22:52</td></tr>'
        for name in entries
    )
    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html><head><title>Index of {title}</title></head><body>
<h1>Index of {title}</h1>
<table>
<tr><th><a href="?C=N;O=D">Name</a></th><th><a href="?C=M;O=A">Last modified</a></th></tr>
<tr><td><a href="/public/e3sm/diagnostic_output/">Parent Directory</a></td><td>&nbsp;</td></tr>
{rows}
</table></body></html>"""


# A faithful miniature of production/v3.LR/v3.LR.historical_0101 as served
# on 2026-10-19: mixed model_vs_obs and model_vs_model subsections, several
# periods, mpas_analysis runs, and sibling directories that must be ignored.
FAKE_ARCHIVE: dict[str, str] = {
    f"{LCRC_ROOT}/e3sm_diags/": _apache_index(
        "e3sm_diags",
        [
            "atm_monthly_180x360_aave/",
            "atm_monthly_180x360_aave_mvm_PI100/",
            "atm_monthly_180x360_aave_mvm/",
            "lnd_monthly_mvm_lnd/",
            "README.txt",
        ],
    ),
    f"{LCRC_ROOT}/e3sm_diags/atm_monthly_180x360_aave/": _apache_index(
        "atm_monthly_180x360_aave",
        ["model_vs_obs_1985-2014/", "model_vs_obs_1995-2024/", "scratch/"],
    ),
    f"{LCRC_ROOT}/e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/": _apache_index(
        "mvm_PI100", ["model_vs_model_1985-2014/"]
    ),
    f"{LCRC_ROOT}/e3sm_diags/atm_monthly_180x360_aave_mvm/": _apache_index(
        "mvm", ["model_vs_model_1985-2014/"]
    ),
    f"{LCRC_ROOT}/e3sm_diags/lnd_monthly_mvm_lnd/": _apache_index(
        "lnd", ["model_vs_model_1995-2024/"]
    ),
    f"{LCRC_ROOT}/mpas_analysis/": _apache_index(
        "mpas_analysis",
        ["ts_1850-2014_climo_1985-2014/", "ts_0001-0500_climo_0451-0500/", "logs/"],
    ),
}


def fake_fetch(url: str, remaining_seconds: float = 30.0) -> FetchResult:
    body = FAKE_ARCHIVE.get(url)
    if body is None:
        return FetchResult(outcome=FetchOutcome.ABSENT)
    return FetchResult(body=body)


def absent_fetch(_url: str, _remaining: float = 30.0) -> FetchResult:
    return FetchResult(outcome=FetchOutcome.ABSENT)


def failing_fetch(_url: str, _remaining: float = 30.0) -> FetchResult:
    return FetchResult(outcome=FetchOutcome.FAILED)


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    discovery_cache.clear()
    yield
    discovery_cache.clear()


# ----------------------------------------------------------------------------
# Index parsing
# ----------------------------------------------------------------------------


class TestParseDirectoryIndex:
    def test_returns_only_relative_child_directories(self):
        html = _apache_index(
            "x", ["alpha/", "beta/", "file.png", "nested/child/", "https://x.test/"]
        )
        assert parse_directory_index(html) == ["alpha", "beta"]

    def test_ignores_parent_and_sort_links(self):
        html = _apache_index("x", [])
        assert parse_directory_index(html) == []

    @pytest.mark.parametrize(
        "name",
        [
            "javascript:alert(1)",
            "%2e%2e",
            ".hidden",
            "a b",
            "bad\x01name",
            "-leading-dash",
        ],
    )
    def test_rejects_names_that_are_not_plain_directories(self, name):
        """These would be joined into a request URL, so they never leave the parser."""
        html = _apache_index("x", [f"{name}/", "good_name/"])
        assert parse_directory_index(html) == ["good_name"]

    def test_tolerates_non_html(self):
        assert parse_directory_index("not html at all") == []
        assert parse_directory_index("") == []


# ----------------------------------------------------------------------------
# Allowlist
# ----------------------------------------------------------------------------


class TestAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            LCRC_ROOT,
            LCRC_ROOT + "/",
            "https://portal.nersc.gov/cfs/e3sm/diagnostics_archive/production/x",
        ],
    )
    def test_reviewed_archive_roots_are_allowed(self, url):
        assert is_allowed_archive_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example/public/e3sm/diagnostic_output/diagnostics_archive/x",
            "http://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive/x",
            "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/ac.someone/case",
            "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive_evil/x",
            "ftp://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive/x",
            "",
        ],
    )
    def test_everything_else_is_refused(self, url):
        assert is_allowed_archive_url(url) is False

    def test_prefixes_can_be_overridden_as_comma_separated_string(self):
        with patch.object(
            settings,
            "diagnostics_viewer_allowed_url_prefixes",
            "https://a.test/archive/, https://b.test/archive",
        ):
            assert is_allowed_archive_url("https://b.test/archive/case") is True
            assert is_allowed_archive_url(LCRC_ROOT) is False


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------


class TestDiscoverDiagnosticsViewers:
    def test_enumerates_e3sm_diags_and_mpas_analysis_runs(self):
        result = discover_diagnostics_viewers(LCRC_ROOT, fake_fetch)

        assert result.error is None
        assert result.truncated is False
        by_tool = {}
        for viewer in result.viewers:
            by_tool.setdefault(viewer.tool, []).append(viewer)

        e3sm = by_tool["e3sm_diags"]
        assert [v.url.removeprefix(LCRC_ROOT + "/") for v in e3sm] == [
            "e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1995-2024/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave_mvm/model_vs_model_1985-2014/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/model_vs_model_1985-2014/viewer/",
            "e3sm_diags/lnd_monthly_mvm_lnd/model_vs_model_1995-2024/viewer/",
        ]
        mpas = by_tool["mpas_analysis"]
        assert [v.url.removeprefix(LCRC_ROOT + "/") for v in mpas] == [
            "mpas_analysis/ts_0001-0500_climo_0451-0500/",
            "mpas_analysis/ts_1850-2014_climo_1985-2014/",
        ]

    def test_parses_periods_comparison_and_reference_hint(self):
        viewers = {
            v.url.removeprefix(LCRC_ROOT + "/"): v
            for v in discover_diagnostics_viewers(LCRC_ROOT, fake_fetch).viewers
        }

        obs = viewers[
            "e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/"
        ]
        assert obs.comparison == "model_vs_obs"
        assert (obs.start_year, obs.end_year) == (1985, 2014)
        assert obs.subsection == "atm_monthly_180x360_aave"
        assert obs.reference_hint is None

        mvm = viewers[
            "e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/model_vs_model_1985-2014/viewer/"
        ]
        assert mvm.comparison == "model_vs_model"
        assert mvm.reference_hint == "PI100"

        bare_mvm = viewers[
            "e3sm_diags/atm_monthly_180x360_aave_mvm/model_vs_model_1985-2014/viewer/"
        ]
        assert bare_mvm.reference_hint is None

        mpas = viewers["mpas_analysis/ts_0001-0500_climo_0451-0500/"]
        assert (mpas.ts_start_year, mpas.ts_end_year) == (1, 500)
        assert (mpas.start_year, mpas.end_year) == (451, 500)
        assert mpas.comparison is None and mpas.subsection is None

    def test_ignores_directories_outside_the_zppy_convention(self):
        urls = {
            v.url for v in discover_diagnostics_viewers(LCRC_ROOT, fake_fetch).viewers
        }
        assert not any("scratch" in u or "logs" in u or "README" in u for u in urls)

    def test_missing_tool_directories_yield_empty_not_error(self):
        result = discover_diagnostics_viewers(LCRC_ROOT, absent_fetch)
        assert result.viewers == ()
        assert result.error is None
        # One probe each for e3sm_diags/ and mpas_analysis/, nothing deeper.
        assert result.requests_made == 2

    def test_unreachable_archive_is_an_error_not_an_empty_listing(self):
        """An outage must not be recorded as "this case has no runs"."""
        result = discover_diagnostics_viewers(LCRC_ROOT, failing_fetch)

        assert result.viewers == ()
        assert result.error == "archive_unavailable"

    def test_one_failed_subdirectory_does_not_discard_the_rest(self):
        def flaky(url: str, remaining: float = 30.0) -> FetchResult:
            if url.endswith("/mpas_analysis/"):
                return FetchResult(outcome=FetchOutcome.FAILED)
            return fake_fetch(url, remaining)

        result = discover_diagnostics_viewers(LCRC_ROOT, flaky)

        assert result.error is None
        assert [v.tool for v in result.viewers] == ["e3sm_diags"] * 5

    def test_refuses_roots_outside_reviewed_archives_without_fetching(self):
        calls: list[str] = []

        def spy(url: str, _remaining: float = 30.0) -> FetchResult:
            calls.append(url)
            return FetchResult(outcome=FetchOutcome.ABSENT)

        result = discover_diagnostics_viewers("https://evil.example/archive/case", spy)
        assert result.error == "root_not_in_reviewed_archive"
        assert result.viewers == ()
        assert calls == []

    def test_request_budget_truncates_rather_than_runs_away(self):
        result = discover_diagnostics_viewers(LCRC_ROOT, fake_fetch, max_requests=2)
        assert result.truncated is True
        assert result.requests_made == 2
        # The two requests were e3sm_diags/ and its first subsection, so the
        # mpas_analysis side never ran and only that subsection's runs exist.
        assert all(v.tool == "e3sm_diags" for v in result.viewers)
        assert len(result.viewers) == 2

    def test_deadline_truncates_a_slow_archive(self):
        # Each listing "takes" 3 seconds on a fake clock; an 8 s deadline
        # allows the first three fetches and then stops, keeping what it has.
        clock = {"now": 1000.0}

        def slow_fetch(url: str, _remaining: float = 30.0) -> FetchResult:
            clock["now"] += 3.0
            return fake_fetch(url)

        with patch(
            "app.features.catalog.diagnostics_viewers.time.monotonic",
            side_effect=lambda: clock["now"],
        ):
            result = discover_diagnostics_viewers(
                LCRC_ROOT, slow_fetch, deadline_seconds=8.0
            )

        assert result.truncated is True
        assert result.requests_made == 3
        # e3sm_diags/, then two subsections: their runs were found before time ran out.
        assert len(result.viewers) == 3
        assert all(v.tool == "e3sm_diags" for v in result.viewers)

    def test_root_trailing_slash_is_normalized(self):
        with_slash = discover_diagnostics_viewers(LCRC_ROOT + "/", fake_fetch)
        without = discover_diagnostics_viewers(LCRC_ROOT, fake_fetch)
        assert [v.url for v in with_slash.viewers] == [v.url for v in without.viewers]


# ----------------------------------------------------------------------------
# HTTP fetcher
# ----------------------------------------------------------------------------


class TestHttpDirectoryFetcher:
    def _fetch(self, handler, **client_kwargs):
        client = httpx.Client(transport=httpx.MockTransport(handler), **client_kwargs)
        return http_directory_fetcher(client)

    def test_returns_body_for_html_200_and_sets_user_agent(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers["user-agent"]
            return httpx.Response(
                200, text="<a href='x/'>x/</a>", headers={"content-type": "text/html"}
            )

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)
        assert result.body == "<a href='x/'>x/</a>"
        assert result.failed is False
        assert seen["ua"].startswith("simboard-diagnostics-viewer-discovery/")

    @pytest.mark.parametrize("status", [403, 404])
    def test_archive_saying_no_index_is_absent_not_failure(self, status):
        """403/404 are the archive answering; they must not look like an outage."""
        result = self._fetch(lambda _r: httpx.Response(status, text="denied"))(
            LCRC_ROOT + "/mpas_analysis/", 30.0
        )
        assert result.outcome is FetchOutcome.ABSENT
        assert result.failed is False

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_errors_are_failures(self, status):
        result = self._fetch(lambda _r: httpx.Response(status, text="boom"))(
            LCRC_ROOT + "/e3sm_diags/", 30.0
        )
        assert result.failed is True

    def test_non_html_200_is_absent(self):
        result = self._fetch(
            lambda _r: httpx.Response(
                200, content=b"\x89PNG", headers={"content-type": "image/png"}
            )
        )(LCRC_ROOT + "/e3sm_diags/", 30.0)
        assert result.outcome is FetchOutcome.ABSENT

    def test_transport_errors_are_failures(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)
        assert result.failed is True

    def test_body_larger_than_the_cap_is_abandoned(self):
        huge = b"<a href='x/'>x/</a>" * 200_000

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=huge, headers={"content-type": "text/html"}
            )

        with patch.object(settings, "diagnostics_viewer_max_index_bytes", 1024):
            result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)

        assert result.failed is True

    def test_body_that_outlasts_the_deadline_is_abandoned(self):
        """A trickling response stays under the read timeout but not the deadline."""
        clock = {"now": 0.0}

        def handler(_request: httpx.Request) -> httpx.Response:
            def stream():
                for _ in range(10):
                    clock["now"] += 1.0
                    yield b"<a href='x/'>x/</a>"

            return httpx.Response(
                200, content=stream(), headers={"content-type": "text/html"}
            )

        with patch(
            "app.features.catalog.diagnostics_viewers.time.monotonic",
            side_effect=lambda: clock["now"],
        ):
            result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 3.0)

        assert result.failed is True

    def test_redirect_within_the_archive_is_followed(self):
        target = LCRC_ROOT + "/e3sm_diags/"

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).endswith("/e3sm_diags"):
                return httpx.Response(301, headers={"location": target})
            return httpx.Response(
                200,
                text="<a href='sub/'>sub/</a>",
                headers={"content-type": "text/html"},
            )

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags", 30.0)
        assert result.body == "<a href='sub/'>sub/</a>"

    @pytest.mark.parametrize(
        "location",
        [
            "https://evil.example/secrets/",
            "http://169.254.169.254/latest/meta-data/",
            "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/ac.someone/",
        ],
    )
    def test_redirect_off_the_reviewed_archives_is_refused(self, location):
        """An allowed host must not be able to steer the backend elsewhere."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if len(requested) == 1:
                return httpx.Response(302, headers={"location": location})
            return httpx.Response(200, text="should never be read")

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)

        assert result.failed is True
        assert len(requested) == 1

    def test_no_request_is_made_once_the_deadline_has_passed(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, text="", headers={"content-type": "text/html"})

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 0.0)

        assert result.failed is True
        assert requested == []

    def test_redirect_without_a_location_header_is_a_failure(self):
        result = self._fetch(lambda _r: httpx.Response(302))(
            LCRC_ROOT + "/e3sm_diags/", 30.0
        )
        assert result.failed is True

    def test_malformed_redirect_target_is_a_failure_not_a_crash(self):
        """httpx.InvalidURL is not an HTTPError and would otherwise escape."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302, headers={"location": "https://web.lcrc.anl.gov/\x01"}
            )

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)
        assert result.failed is True

    def test_redirect_loop_stops_at_the_limit(self):
        hops: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hops.append(str(request.url))
            return httpx.Response(302, headers={"location": LCRC_ROOT + "/e3sm_diags/"})

        result = self._fetch(handler)(LCRC_ROOT + "/e3sm_diags/", 30.0)
        assert result.failed is True
        assert len(hops) <= 4


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------


class TestDiscoveryCache:
    def _result(self, root: str) -> DiscoveryResult:
        return DiscoveryResult(
            root_url=root, viewers=(), requests_made=1, truncated=False
        )

    def test_round_trip_and_expiry(self):
        cache = DiscoveryCache(ttl_seconds=60)
        cache.put("r", self._result("r"))
        assert cache.get("r") is not None

        with patch("app.features.catalog.diagnostics_viewers.time.monotonic") as clock:
            clock.return_value = 10**9
            assert cache.get("r") is None
        assert cache.get("missing") is None

    def test_evicts_oldest_once_full(self):
        cache = DiscoveryCache(ttl_seconds=60, max_entries=2)
        cache.put("a", self._result("a"))
        cache.put("b", self._result("b"))
        cache.put("c", self._result("c"))
        assert len(cache) == 2
        assert cache.get("a") is None
        assert cache.get("b") is not None and cache.get("c") is not None

    def test_put_purges_expired_before_evicting_live_entries(self):
        cache = DiscoveryCache(ttl_seconds=60, max_entries=2)
        with patch("app.features.catalog.diagnostics_viewers.time.monotonic") as clock:
            clock.return_value = 0.0
            cache.put("stale", self._result("stale"))
            clock.return_value = 30.0
            cache.put("live", self._result("live"))
            clock.return_value = (
                70.0  # "stale" (expires 60) is gone, "live" (expires 90) is not
            )
            cache.put("new", self._result("new"))
            assert len(cache) == 2
            assert cache.get("stale") is None
            assert cache.get("live") is not None
            assert cache.get("new") is not None

    def test_discover_with_cache_reuses_result_and_skips_errors(self):
        calls = {"n": 0}

        def fake_discover(root_url, fetch):
            calls["n"] += 1
            error = "root_not_in_reviewed_archive" if "bad" in root_url else None
            return DiscoveryResult(root_url, (), 0, False, error=error)

        with patch(
            "app.features.catalog.diagnostics_viewers.discover_diagnostics_viewers",
            side_effect=fake_discover,
        ):
            discover_with_cache(LCRC_ROOT)
            discover_with_cache(LCRC_ROOT)
            assert calls["n"] == 1

            discover_with_cache(LCRC_ROOT + "-bad")
            discover_with_cache(LCRC_ROOT + "-bad")
            assert calls["n"] == 3


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------


def _case_with_links(
    db: Session, name: str, links: list[tuple[ExternalLinkKind, str, str | None]]
) -> Case:
    machine = db.query(Machine).first()
    assert machine is not None
    case = Case(name=name, machine_id=machine.id, hpc_username="wlin")
    db.add(case)
    db.flush()
    for kind, url, label in links:
        db.add(ExternalLink(case_id=case.id, kind=kind, url=url, label=label))
    db.commit()
    return case


class TestCaseDiagnosticsViewersEndpoint:
    def test_404_for_unknown_case(self, client):
        from uuid import uuid4

        res = client.get(f"{API_BASE}/cases/{uuid4()}/diagnostics/viewers")
        assert res.status_code == 404

    def test_case_without_diagnostic_links_has_no_sources(self, client, db: Session):
        case = _case_with_links(
            db,
            "no-diags",
            [(ExternalLinkKind.DOCS, "https://example.com/docs", "Docs")],
        )
        res = client.get(f"{API_BASE}/cases/{case.id}/diagnostics/viewers")
        assert res.status_code == 200
        body = res.json()
        assert body["caseId"] == str(case.id)
        assert body["caseName"] == "no-diags"
        assert body["sources"] == []

    def test_discovers_viewers_for_each_diagnostic_link(self, client, db: Session):
        case = _case_with_links(
            db,
            "v3.LR.historical_0101",
            [
                (ExternalLinkKind.DIAGNOSTIC, LCRC_ROOT, "zppy diagnostics"),
                (ExternalLinkKind.PERFORMANCE, "https://pace.ornl.gov/exp/1", "PACE"),
            ],
        )

        def fake_discover(root_url: str) -> DiscoveryResult:
            return discover_diagnostics_viewers(root_url, fake_fetch)

        with patch(
            "app.features.catalog.api.discover_with_cache", side_effect=fake_discover
        ):
            res = client.get(f"{API_BASE}/cases/{case.id}/diagnostics/viewers")

        assert res.status_code == 200
        body = res.json()
        assert len(body["sources"]) == 1
        source = body["sources"][0]
        assert source["rootUrl"] == LCRC_ROOT
        assert source["label"] == "zppy diagnostics"
        assert source["error"] is None
        assert source["truncated"] is False
        assert len(source["viewers"]) == 7

        first = source["viewers"][0]
        assert first == {
            "tool": "e3sm_diags",
            "url": f"{LCRC_ROOT}/e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/",
            "subsection": "atm_monthly_180x360_aave",
            "comparison": "model_vs_obs",
            "startYear": 1985,
            "endYear": 2014,
            "tsStartYear": None,
            "tsEndYear": None,
            "referenceHint": None,
        }
        mvm = next(v for v in source["viewers"] if v["referenceHint"] == "PI100")
        assert mvm["comparison"] == "model_vs_model"
        mpas = next(v for v in source["viewers"] if v["tool"] == "mpas_analysis")
        assert mpas["url"].endswith("/mpas_analysis/ts_0001-0500_climo_0451-0500/")
        assert (mpas["tsStartYear"], mpas["tsEndYear"]) == (1, 500)

    def test_unreviewed_root_is_reported_not_fatal(self, client, db: Session):
        case = _case_with_links(
            db,
            "legacy-diags",
            [
                (
                    ExternalLinkKind.DIAGNOSTIC,
                    "https://e3sm.org/diagnostics/piControl",
                    "Dashboard",
                )
            ],
        )
        res = client.get(f"{API_BASE}/cases/{case.id}/diagnostics/viewers")
        assert res.status_code == 200
        source = res.json()["sources"][0]
        assert source["viewers"] == []
        assert source["error"] == "root_not_in_reviewed_archive"
