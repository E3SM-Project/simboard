"""Lining up plots across runs, and the comparison endpoint."""

from unittest.mock import patch

import pytest

from app.api.version import API_BASE
from app.features.diagnostics import catalog as catalog_module
from app.features.diagnostics.compare import group_plots, panels, shared_sets
from app.features.diagnostics.e3sm_diags import plot_from_path
from app.features.diagnostics.plots import Catalog, Plot, PlotSet

LCRC = "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output"
HIST = f"{LCRC}/x/v3.LR.historical/e3sm_diags/a/model_vs_obs_1985-2014/viewer/"
PICTL = f"{LCRC}/x/v3.LR.piControl/e3sm_diags/a/model_vs_obs_1985-2014/viewer/"


def e3sm(paths: list[str]) -> PlotSet:
    plots = [plot_from_path(p.split("/")[0], p) for p in paths]
    name = paths[0].split("/")[0]
    return PlotSet(name, name.title(), tuple(p for p in plots if p))


def run(url: str, *sets: PlotSet, error: str | None = None) -> Catalog:
    return Catalog(url, "e3sm_diags", url.removesuffix("viewer/"), sets, error=error)


LAT_LON = [
    "lat_lon/GPCP/GPCP-PRECT-DJF-global.png",
    "lat_lon/GPCP/GPCP-PRECT-ANN-global.png",
    "lat_lon/ERA5/ERA5-U-850-ANN-global.png",
]


class TestSharedSets:
    def test_keeps_only_plots_every_run_has(self):
        a = run(HIST, e3sm(LAT_LON), e3sm(["polar/X/X-PRECT-ANN-polar_N.png"]))
        b = run(PICTL, e3sm(LAT_LON[:2]))

        (shared,) = shared_sets([a, b])
        assert shared.name == "lat_lon"
        assert [p.key for p in shared.plots] == [
            "lat_lon/GPCP/PRECT-DJF-global",
            "lat_lon/GPCP/PRECT-ANN-global",
        ]
        assert shared.missing == 1

    def test_unreadable_runs_are_left_out(self):
        a = run(HIST, e3sm(LAT_LON))
        broken = run(PICTL, error="catalog_unavailable")
        assert len(shared_sets([a, broken])[0].plots) == 3

    def test_nothing_readable_is_nothing_shared(self):
        assert shared_sets([run(HIST, error="x")]) == []


def test_groups_order_seasons_and_keep_regions_in_page_order():
    (shared,) = shared_sets([run(HIST, e3sm(LAT_LON))])
    groups = group_plots(shared.plots)

    assert [(g.title, g.reference) for g in groups] == [
        ("PRECT", "GPCP"),
        ("U-850", "ERA5"),
    ]
    assert [p.season for p in groups[0].plots] == ["ANN", "DJF"]


def test_mpas_runs_have_no_panels():
    assert panels("mpas_analysis", "lat_lon") == {}
    assert set(panels("e3sm_diags", "lat_lon")) == {"test", "ref", "diff"}
    assert set(panels("e3sm_diags", "zonal_mean_xy")) == {"test", "diff"}


class TestCompareEndpoint:
    def _post(self, client, catalogs: dict[str, Catalog], body: dict, **kwargs):
        def fake(url, label=""):
            return catalogs[url]

        with patch("app.features.diagnostics.api.read_catalog_cached", fake):
            return client.post(f"{API_BASE}/diagnostics/compare", json=body, **kwargs)

    def test_returns_shared_sets_and_the_first_in_detail(self, client):
        mvm_a = "lat_lon/model_vs_model/v3.LR.piControl-PRECT-ANN-global.png"
        mvm_b = "lat_lon/model_vs_model/v3.LR.amip-PRECT-ANN-global.png"
        catalogs = {HIST: run(HIST, e3sm([mvm_a])), PICTL: run(PICTL, e3sm([mvm_b]))}
        res = self._post(
            client,
            catalogs,
            {"runs": [{"url": HIST, "label": "Historical"}, {"url": PICTL}]},
        )

        assert res.status_code == 200
        body = res.json()
        assert [r["label"] for r in body["runs"]] == ["Historical", ""]
        assert body["runs"][0]["imageBaseUrl"] == HIST.removesuffix("viewer/")
        assert body["sets"] == [
            {"name": "lat_lon", "title": "Lat_Lon", "plotCount": 1, "missing": 0}
        ]
        detail = body["set"]
        assert detail["imageWidth"] == 1275
        assert detail["panels"]["test"] == {
            "width": 1050,
            "height": 505,
            "top": 60,
            "left": 165,
        }
        (group,) = detail["groups"]
        (plot,) = group["plots"]
        assert plot["paths"] == [mvm_a, mvm_b]
        assert plot["references"] == ["v3.LR.piControl", "v3.LR.amip"]

    def test_details_the_requested_set(self, client):
        polar = e3sm(["polar/X/X-PRECT-ANN-polar_N.png"])
        catalogs = {HIST: run(HIST, e3sm(LAT_LON), polar)}
        body = self._post(
            client, catalogs, {"runs": [{"url": HIST}], "set": "polar"}
        ).json()
        assert body["set"]["name"] == "polar"
        assert len(body["sets"]) == 2

    def test_an_unreadable_run_is_reported_and_left_out(self, client):
        catalogs = {
            HIST: run(HIST, e3sm(LAT_LON)),
            PICTL: run(PICTL, error="url_not_allowed"),
        }
        body = self._post(
            client, catalogs, {"runs": [{"url": HIST}, {"url": PICTL}]}
        ).json()
        assert body["runs"][1]["error"] == "url_not_allowed"
        assert body["set"]["groups"][0]["plots"][0]["paths"][1] is None

    def test_supports_conditional_requests(self, client):
        catalogs = {HIST: run(HIST, e3sm(LAT_LON))}
        body = {"runs": [{"url": HIST}]}
        etag = self._post(client, catalogs, body).headers["etag"]
        again = self._post(client, catalogs, body, headers={"If-None-Match": etag})
        assert again.status_code == 304

    @pytest.mark.parametrize(
        "body", [{"runs": []}, {"runs": [{"url": HIST}] * 13}, {"runs": [{"url": ""}]}]
    )
    def test_rejects_bad_requests(self, client, body):
        assert (
            client.post(f"{API_BASE}/diagnostics/compare", json=body).status_code == 422
        )


class TestReadCatalogCached:
    MPAS = f"{LCRC}/ac.x/case/yrs1-10/"

    def setup_method(self):
        catalog_module._cache.clear()

    def test_dispatches_by_url(self):
        assert catalog_module.read_catalog(
            "https://h.test/x", lambda *_: None
        ).error == ("unrecognized_url")

    def test_mpas_labels_are_part_of_the_key(self):
        calls = []

        def fake(url, fetch, label=""):
            calls.append(label)
            return Catalog(url, "mpas_analysis", url)

        with (
            patch.object(catalog_module, "read_catalog", fake),
            patch.object(catalog_module, "with_http_fetcher", lambda read: read(None)),
        ):
            for label in ("!a", "!a", "!b", "plain", "other"):
                catalog_module.read_catalog_cached(self.MPAS, label)
        # "!a" read once; the two plain labels share the unlabelled entry.
        assert calls == ["!a", "!b", "plain"]


def test_plot_defaults():
    assert Plot("k", "p", "g", "t", "r").single_panel is False
