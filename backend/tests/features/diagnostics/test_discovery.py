"""Finding a case's diagnostics runs from the archive's directory listings."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.models import Case, ExternalLink
from app.features.diagnostics import discovery
from app.features.diagnostics.archive import ABSENT, FAILED, FetchResult
from app.features.diagnostics.discovery import discover_runs, parse_directory_index
from app.features.machine.models import Machine

ROOT = (
    "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive"
    "/production/v3.LR/v3.LR.historical_0101"
)


def apache_index(entries: list[str]) -> str:
    """An Apache listing, with the parent and sort links real ones carry."""
    rows = "".join(f'<tr><td><a href="{e}">{e}</a></td></tr>' for e in entries)
    return (
        '<table><tr><th><a href="?C=N;O=D">Name</a></th></tr>'
        '<tr><td><a href="/public/e3sm/">Parent Directory</a></td></tr>'
        f"{rows}</table>"
    )


# A miniature of v3.LR.historical_0101 as published: observation and
# model-vs-model subsections, two periods, MPAS runs, and noise to ignore.
ARCHIVE = {
    f"{ROOT}/e3sm_diags/": apache_index(
        [
            "atm_monthly_180x360_aave/",
            "atm_monthly_180x360_aave_mvm_PI100/",
            "atm_monthly_180x360_aave_mvm/",
            "README.txt",
        ]
    ),
    f"{ROOT}/e3sm_diags/atm_monthly_180x360_aave/": apache_index(
        ["model_vs_obs_1985-2014/", "model_vs_obs_1995-2024/", "scratch/"]
    ),
    f"{ROOT}/e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/": apache_index(
        ["model_vs_model_1985-2014/"]
    ),
    f"{ROOT}/e3sm_diags/atm_monthly_180x360_aave_mvm/": apache_index(
        ["model_vs_model_1985-2014/"]
    ),
    f"{ROOT}/mpas_analysis/": apache_index(
        ["ts_1850-2014_climo_1985-2014/", "ts_0001-0500_climo_0451-0500/", "logs/"]
    ),
}


def fetch(url: str, _remaining: float = 30.0) -> FetchResult:
    body = ARCHIVE.get(url)
    return FetchResult(body=body) if body else ABSENT


@pytest.fixture(autouse=True)
def _clear_cache():
    discovery._cache.clear()
    yield
    discovery._cache.clear()


class TestParseDirectoryIndex:
    def test_keeps_only_child_directories(self):
        html = apache_index(["alpha/", "beta/", "file.png", "a/b/", "https://x.test/"])
        assert parse_directory_index(html) == ["alpha", "beta"]

    @pytest.mark.parametrize(
        "name", ["javascript:alert(1)", "%2e%2e", ".hidden", "a b", "bad\x01", "-x"]
    )
    def test_drops_names_unsafe_to_put_in_a_url(self, name):
        html = apache_index([f"{name}/", "good/"])
        assert parse_directory_index(html) == ["good"]

    def test_tolerates_anything(self):
        assert parse_directory_index("not html") == []


class TestDiscoverRuns:
    def test_finds_every_run(self):
        result = discover_runs(ROOT, fetch)

        assert result.error is None and not result.truncated
        assert [r.url.removeprefix(ROOT + "/") for r in result.runs] == [
            "e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1995-2024/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave_mvm/model_vs_model_1985-2014/viewer/",
            "e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/model_vs_model_1985-2014/viewer/",
            "mpas_analysis/ts_0001-0500_climo_0451-0500/",
            "mpas_analysis/ts_1850-2014_climo_1985-2014/",
        ]

    def test_reads_periods_and_kind(self):
        runs = {
            r.url.removeprefix(ROOT + "/"): r for r in discover_runs(ROOT, fetch).runs
        }

        obs = runs["e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/"]
        assert (obs.comparison, obs.start_year, obs.end_year) == (
            "model_vs_obs",
            1985,
            2014,
        )

        mvm = "e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/model_vs_model_1985-2014/viewer/"
        assert runs[mvm].comparison == "model_vs_model"

        mpas = runs["mpas_analysis/ts_0001-0500_climo_0451-0500/"]
        assert (mpas.ts_start_year, mpas.ts_end_year, mpas.start_year) == (1, 500, 451)

    def test_no_output_is_empty_not_an_error(self):
        result = discover_runs(ROOT, lambda _u, _r: ABSENT)
        assert result.runs == () and result.error is None

    def test_an_outage_is_an_error_not_an_empty_case(self):
        assert discover_runs(ROOT, lambda _u, _r: FAILED).error == "archive_unavailable"

    def test_one_failed_listing_keeps_the_rest(self):
        def flaky(url, remaining=30.0):
            return FAILED if url.endswith("/mpas_analysis/") else fetch(url)

        result = discover_runs(ROOT, flaky)
        assert result.error is None
        assert {r.tool for r in result.runs} == {"e3sm_diags"}

    def test_refuses_other_hosts_without_fetching(self):
        calls = []
        result = discover_runs(
            "https://evil.example/case", lambda u, _r: calls.append(u)
        )
        assert result.error == "url_not_allowed" and calls == []

    def test_budget_truncates_and_keeps_what_it_found(self):
        result = discover_runs(ROOT, fetch, max_requests=2)
        assert result.truncated
        assert len(result.runs) == 2

    def test_cache_skips_errors(self):
        calls = []

        def fake(root, fetch):
            calls.append(root)
            return discovery.Discovery(root, (), error="x" if "bad" in root else None)

        with (
            patch.object(discovery, "discover_runs", fake),
            patch.object(discovery, "with_http_fetcher", lambda read: read(None)),
        ):
            for root in (ROOT, ROOT, ROOT + "bad", ROOT + "bad"):
                discovery.discover_runs_cached(root)
        assert len(calls) == 3


def _case(db: Session, links: list[tuple[ExternalLinkKind, str]]) -> Case:
    machine = db.query(Machine).first()
    assert machine is not None
    case = Case(name="v3.LR.historical_0101", machine_id=machine.id, hpc_username="u")
    db.add(case)
    db.flush()
    for kind, url in links:
        db.add(ExternalLink(case_id=case.id, kind=kind, url=url, label="zppy"))
    db.commit()
    return case


class TestCaseDiagnosticsRunsEndpoint:
    def test_unknown_case_is_404(self, client):
        assert (
            client.get(f"{API_BASE}/cases/{uuid4()}/diagnostics/runs").status_code
            == 404
        )

    def test_lists_runs_for_each_diagnostic_link(self, client, db: Session):
        case = _case(
            db,
            [
                (ExternalLinkKind.DIAGNOSTIC, ROOT),
                (ExternalLinkKind.PERFORMANCE, "https://pace.ornl.gov/exp/1"),
            ],
        )
        with patch(
            "app.features.diagnostics.api.discover_runs_cached",
            lambda root: discover_runs(root, fetch),
        ):
            body = client.get(f"{API_BASE}/cases/{case.id}/diagnostics/runs").json()

        assert body["caseName"] == "v3.LR.historical_0101"
        (source,) = body["sources"]
        assert source["rootUrl"] == ROOT and source["label"] == "zppy"
        assert len(source["runs"]) == 6
        assert source["runs"][0] == {
            "tool": "e3sm_diags",
            "url": f"{ROOT}/e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/",
            "subsection": "atm_monthly_180x360_aave",
            "comparison": "model_vs_obs",
            "startYear": 1985,
            "endYear": 2014,
            "tsStartYear": None,
            "tsEndYear": None,
        }

    def test_unreadable_root_is_reported_not_fatal(self, client, db: Session):
        case = _case(db, [(ExternalLinkKind.DIAGNOSTIC, "https://e3sm.org/diags")])
        (source,) = client.get(f"{API_BASE}/cases/{case.id}/diagnostics/runs").json()[
            "sources"
        ]
        assert source["runs"] == [] and source["error"] == "url_not_allowed"
