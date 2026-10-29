"""Reading an E3SM Diags run's plots from its own viewer pages.

Fixtures are excerpts of real viewer pages from v3.LR.historical_0101 on the
LCRC diagnostics archive.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.diagnostics.archive import ABSENT, FetchResult
from app.features.diagnostics.e3sm_diags import (
    normalize_url,
    parse_filename,
    parse_set_page,
    parse_viewer_index,
    plot_from_path,
    read_catalog,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "diagnostics"
VIEWER = (
    "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive"
    "/production/v3.LR/v3.LR.historical_0101/e3sm_diags/atm_monthly_180x360_aave"
    "/model_vs_obs_1985-2014/viewer/"
)


def fixture(name: str) -> str:
    return (FIXTURES / f"e3sm_diags_{name}.html").read_text()


def site(pages: dict[str, str]):
    calls: list[str] = []

    def fetch(url: str, _remaining: float = 30.0) -> FetchResult:
        calls.append(url)
        return FetchResult(body=pages[url]) if url in pages else ABSENT

    return fetch, calls


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("GPCP_v2.3-PRECT-ANN-global.png", ("PRECT", "ANN", "global")),
        ("CERES-EBAF-TOA-v4.1-SWCF-JJA-global.png", ("SWCF", "JJA", "global")),
        ("ERA5-U-850-DJF-global.png", ("U-850", "DJF", "global")),
        ("GPCP_v3.2-PRECT-MAM-polar_S.png", ("PRECT", "MAM", "polar_S")),
        ("TRMM-3B43v-7_3hr-PRECT-JJA-20S20N.png", ("PRECT", "JJA", "20S20N")),
        ("v3.LR.piControl-PRECT-ANN-global.png", ("PRECT", "ANN", "global")),
        ("GPCP_v3.2-PRECT-Annual-Cycle.png", ("PRECT", None, None)),
        ("qbo_diags.png", ("qbo_diags", None, None)),
    ],
)
def test_parse_filename(filename, expected):
    assert parse_filename(filename) == expected


def test_model_vs_model_plots_line_up_across_reference_cases():
    pi = plot_from_path(
        "lat_lon", "lat_lon/model_vs_model/v3.LR.piControl-PRECT-ANN-global.png"
    )
    amip = plot_from_path(
        "lat_lon", "lat_lon/model_vs_model/v3.LR.amip_0101-PRECT-ANN-global.png"
    )
    assert pi and amip
    assert pi.key == amip.key == "lat_lon/model_vs_model/PRECT-ANN-global"
    assert (pi.reference, amip.reference) == ("v3.LR.piControl", "v3.LR.amip_0101")


def test_annual_cycle_and_unparsed_names_keep_a_stable_key():
    a = plot_from_path(
        "annual_cycle_zonal_mean", "annual_cycle_zonal_mean/x/a-PRECT-Annual-Cycle.png"
    )
    b = plot_from_path(
        "annual_cycle_zonal_mean", "annual_cycle_zonal_mean/x/b-PRECT-Annual-Cycle.png"
    )
    assert a and b and a.key == b.key
    qbo = plot_from_path("qbo", "qbo/QBO-ERA-Interim/qbo_diags.png")
    assert qbo and qbo.key == "qbo/QBO-ERA-Interim/qbo_diags.png"


def test_viewer_index_lists_sets_with_titles():
    sets = parse_viewer_index(fixture("viewer_index"))
    assert sets["lat_lon"] == "Latitude-Longitude contour maps"
    assert {"polar", "zonal_mean_xy", "qbo", "table", "taylor"} <= set(sets)


def test_set_page_reads_real_previews():
    plots = parse_set_page(fixture("lat_lon_index"), "lat_lon")

    assert len(plots) == 20
    first = plots[0]
    assert first.path == "lat_lon/GPCP_v3.2/GPCP_v3.2-PRECT-ANN-global.png"
    assert first.key == "lat_lon/GPCP_v3.2/PRECT-ANN-global"
    assert first.group == "lat_lon/GPCP_v3.2/PRECT"
    assert (first.title, first.reference) == ("PRECT", "GPCP_v3.2")
    assert {p.season for p in plots} == {"ANN", "DJF", "MAM", "JJA", "SON"}


def test_set_page_model_vs_model():
    plots = parse_set_page(fixture("mvm_polar_index"), "polar")
    assert len(plots) == 12
    assert plots[0].reference == "v3.LR.piControl"
    assert "v3.LR" not in plots[0].key


def test_set_page_decodes_and_skips_what_does_not_belong():
    html = """
    <a data-preview="../../lat_lon/Cloud%20Calipso/CALIPSOCOSP-CLDHGH_CAL-ANN-global.png">a</a>
    <a data-preview="../../lat_lon/Cloud Calipso/CALIPSOCOSP-CLDHGH_CAL-ANN-global.png">b</a>
    <a data-preview="../../polar/X/X-PRECT-ANN-polar_N.png">c</a>
    <a data-preview="../../lat_lon/A/B/too-deep.png">d</a>
    <a data-preview="../../lat_lon/X/X-PRECT-ANN-global.pdf">e</a>
    """
    assert [p.path for p in parse_set_page(html, "lat_lon")] == [
        "lat_lon/Cloud Calipso/CALIPSOCOSP-CLDHGH_CAL-ANN-global.png"
    ]


@pytest.mark.parametrize(
    "url", [VIEWER, VIEWER.rstrip("/"), VIEWER + "index.html", f" {VIEWER} "]
)
def test_normalize_url(url):
    assert normalize_url(url) == VIEWER


class TestReadCatalog:
    PAGES = {
        VIEWER + "index.html": fixture("viewer_index"),
        VIEWER + "lat_lon/index.html": fixture("lat_lon_index"),
    }

    def test_reads_one_page_per_supported_set(self):
        fetch, calls = site(self.PAGES)
        catalog = read_catalog(VIEWER, fetch)

        assert catalog.error is None and not catalog.truncated
        assert catalog.image_base_url == VIEWER.removesuffix("viewer/")
        assert [(s.name, s.title) for s in catalog.sets] == [
            ("lat_lon", "Latitude-Longitude contour maps")
        ]
        for skipped in ("table", "taylor", "cmip6", "tropical_subseasonal"):
            assert VIEWER + f"{skipped}/index.html" not in calls

    def test_missing_viewer_is_unavailable(self):
        assert read_catalog(VIEWER, site({})[0]).error == "catalog_unavailable"

    def test_refuses_other_hosts_without_fetching(self):
        fetch, calls = site({})
        assert (
            read_catalog("https://evil.example/viewer/", fetch).error
            == "url_not_allowed"
        )
        assert calls == []

    def test_stops_at_the_request_budget(self):
        fetch, calls = site(self.PAGES)
        assert read_catalog(VIEWER, fetch, max_requests=2).truncated
        assert len(calls) == 2

    def test_stops_at_the_deadline(self):
        clock = {"now": 0.0}
        fetch, calls = site(self.PAGES)

        def slow(url, remaining=30.0):
            clock["now"] += 5.0
            return fetch(url, remaining)

        with patch(
            "app.features.diagnostics.archive.time.monotonic",
            side_effect=lambda: clock["now"],
        ):
            assert read_catalog(VIEWER, slow, deadline_seconds=12.0).truncated
        assert len(calls) == 3
