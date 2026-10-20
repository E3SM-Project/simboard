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


def fake_fetch(url: str) -> str | None:
    return FAKE_ARCHIVE.get(url)


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
        result = discover_diagnostics_viewers(LCRC_ROOT, lambda _url: None)
        assert result.viewers == ()
        assert result.error is None
        # One probe each for e3sm_diags/ and mpas_analysis/, nothing deeper.
        assert result.requests_made == 2

    def test_refuses_roots_outside_reviewed_archives_without_fetching(self):
        calls: list[str] = []

        def spy(url: str) -> str | None:
            calls.append(url)
            return None

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

    def test_root_trailing_slash_is_normalized(self):
        with_slash = discover_diagnostics_viewers(LCRC_ROOT + "/", fake_fetch)
        without = discover_diagnostics_viewers(LCRC_ROOT, fake_fetch)
        assert [v.url for v in with_slash.viewers] == [v.url for v in without.viewers]


# ----------------------------------------------------------------------------
# HTTP fetcher
# ----------------------------------------------------------------------------


class TestHttpDirectoryFetcher:
    def _client(self, handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_returns_body_for_html_200_and_sets_user_agent(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers["user-agent"]
            return httpx.Response(
                200, text="<a href='x/'>x/</a>", headers={"content-type": "text/html"}
            )

        fetch = http_directory_fetcher(self._client(handler))
        assert fetch("https://x.test/") == "<a href='x/'>x/</a>"
        assert seen["ua"].startswith("simboard-diagnostics-viewer-discovery/")

    @pytest.mark.parametrize("status", [403, 404, 500])
    def test_non_200_is_no_listing(self, status):
        fetch = http_directory_fetcher(
            self._client(lambda _r: httpx.Response(status, text="<html>denied</html>"))
        )
        assert fetch("https://x.test/") is None

    def test_non_html_200_is_no_listing(self):
        fetch = http_directory_fetcher(
            self._client(
                lambda _r: httpx.Response(
                    200, content=b"\x89PNG", headers={"content-type": "image/png"}
                )
            )
        )
        assert fetch("https://x.test/") is None

    def test_transport_errors_are_no_listing(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        fetch = http_directory_fetcher(self._client(handler))
        assert fetch("https://x.test/") is None


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
