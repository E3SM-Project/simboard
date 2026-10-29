"""Archive access: allowlist, fetch outcomes, limits, redirects and cache."""

from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.features.diagnostics.archive import (
    ABSENT,
    FAILED,
    Budget,
    FetchOutcome,
    FetchResult,
    TTLCache,
    http_fetcher,
    is_allowed_url,
)

ROOT = (
    "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive"
    "/production/v3.LR/v3.LR.historical_0101"
)
CLOCK = "app.features.diagnostics.archive.time.monotonic"


class TestAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            ROOT,
            ROOT + "/",
            "https://portal.nersc.gov/cfs/e3sm/diagnostics_archive/production/x",
            "https://portal.nersc.gov/project/m2136/E3SMv1/x",
            "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/ac.someone/x",
        ],
    )
    def test_public_e3sm_roots_are_allowed(self, url):
        assert is_allowed_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example/public/e3sm/x",
            "http://web.lcrc.anl.gov/public/e3sm/x",
            "https://web.lcrc.anl.gov/private/e3sm/x",
            "https://web.lcrc.anl.gov/public/e3sm-private/x",
            "https://portal.nersc.gov/cfs/private/e3sm/x",
            "ftp://web.lcrc.anl.gov/public/e3sm/x",
            "",
        ],
    )
    def test_everything_else_is_refused(self, url):
        assert not is_allowed_url(url)

    def test_prefixes_accept_a_comma_separated_string(self):
        with patch.object(
            settings,
            "diagnostics_allowed_url_prefixes",
            "https://a.test/x, https://b.test/y",
        ):
            assert is_allowed_url("https://b.test/y/run")
            assert not is_allowed_url(ROOT)


class TestBudget:
    def test_stops_at_the_request_limit(self):
        budget = Budget(max_requests=1, deadline_seconds=60)
        assert budget.fetch(lambda _u, _r: ABSENT, ROOT) is ABSENT
        assert budget.fetch(lambda _u, _r: ABSENT, ROOT) is None
        assert budget.truncated and budget.requests_made == 1

    def test_remembers_a_failure(self):
        budget = Budget(max_requests=5, deadline_seconds=60)
        budget.fetch(lambda _u, _r: FAILED, ROOT)
        budget.fetch(lambda _u, _r: ABSENT, ROOT)
        assert budget.failed


class TestHttpFetcher:
    def _fetch(self, handler, remaining=30.0, url=ROOT + "/e3sm_diags/"):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return http_fetcher(client)(url, remaining)

    @staticmethod
    def _html(text="<a href='x/'>x/</a>"):
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})

    def test_returns_the_body_and_identifies_itself(self):
        seen = {}

        def handler(request):
            seen["ua"] = request.headers["user-agent"]
            return self._html()

        assert self._fetch(handler).body == "<a href='x/'>x/</a>"
        assert seen["ua"].startswith("simboard-diagnostics/")

    @pytest.mark.parametrize("status", [403, 404])
    def test_no_index_is_absent_not_failed(self, status):
        assert (
            self._fetch(lambda _r: httpx.Response(status)).outcome
            is FetchOutcome.ABSENT
        )

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_errors_fail(self, status):
        assert self._fetch(lambda _r: httpx.Response(status)).failed

    def test_non_html_is_absent(self):
        response = httpx.Response(
            200, content=b"\x89PNG", headers={"content-type": "image/png"}
        )
        assert self._fetch(lambda _r: response).outcome is FetchOutcome.ABSENT

    def test_transport_errors_fail(self):
        def handler(_request):
            raise httpx.ConnectTimeout("timed out")

        assert self._fetch(handler).failed

    def test_oversized_body_is_abandoned(self):
        with patch.object(settings, "diagnostics_max_page_bytes", 1024):
            assert self._fetch(lambda _r: self._html("x" * 4096)).failed

    def test_trickling_body_is_abandoned_at_the_deadline(self):
        clock = {"now": 0.0}

        def handler(_request):
            def stream():
                for _ in range(10):
                    clock["now"] += 1.0
                    yield b"<a href='x/'>x/</a>"

            return httpx.Response(
                200, content=stream(), headers={"content-type": "text/html"}
            )

        with patch(CLOCK, side_effect=lambda: clock["now"]):
            assert self._fetch(handler, remaining=3.0).failed

    def test_nothing_is_requested_after_the_deadline(self):
        requested = []

        def handler(request):
            requested.append(request.url)
            return self._html()

        assert self._fetch(handler, remaining=0.0).failed
        assert requested == []

    def test_redirect_within_the_archive_is_followed(self):
        def handler(request):
            if str(request.url).endswith("/e3sm_diags"):
                return httpx.Response(301, headers={"location": ROOT + "/e3sm_diags/"})
            return self._html()

        assert self._fetch(handler, url=ROOT + "/e3sm_diags").body

    @pytest.mark.parametrize(
        "location",
        [
            "https://evil.example/secrets/",
            "http://169.254.169.254/latest/meta-data/",
            "https://web.lcrc.anl.gov/private/e3sm/x/",
        ],
    )
    def test_redirect_off_the_allowed_hosts_is_refused(self, location):
        requested = []

        def handler(request):
            requested.append(request.url)
            return httpx.Response(302, headers={"location": location})

        assert self._fetch(handler).failed
        assert len(requested) == 1

    @pytest.mark.parametrize(
        "headers", [{}, {"location": "https://web.lcrc.anl.gov/\x01"}]
    )
    def test_bad_redirects_fail_without_raising(self, headers):
        assert self._fetch(lambda _r: httpx.Response(302, headers=headers)).failed

    def test_redirect_loops_stop(self):
        hops = []

        def handler(request):
            hops.append(request.url)
            return httpx.Response(302, headers={"location": ROOT + "/e3sm_diags/"})

        assert self._fetch(handler).failed
        assert len(hops) == 4


class TestTTLCache:
    def test_round_trip_and_expiry(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60)
        cache.put("k", "v")
        assert cache.get("k") == "v"
        with patch(CLOCK, return_value=10**9):
            assert cache.get("k") is None

    def test_evicts_the_oldest_once_full(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=2)
        for key in "abc":
            cache.put(key, key)
        assert len(cache) == 2
        assert cache.get("a") is None

    def test_expired_entries_go_before_live_ones(self):
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=2)
        with patch(CLOCK) as clock:
            clock.return_value = 0.0
            cache.put("stale", "x")
            clock.return_value = 30.0
            cache.put("live", "x")
            clock.return_value = 70.0
            cache.put("new", "x")
            assert cache.get("stale") is None
            assert cache.get("live") == cache.get("new") == "x"


def test_fetch_result_failed_flag():
    assert FetchResult(outcome=FetchOutcome.FAILED).failed
    assert not FetchResult(body="x").failed
