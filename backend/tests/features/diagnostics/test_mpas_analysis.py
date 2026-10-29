"""Reading an MPAS-Analysis run's plots from its gallery pages.

Fixtures are excerpts of real galleries on LCRC: v3.LR.historical_0101, and
the cryosphere run from IICE's MPAS demo, which uses an older layout.
"""

from pathlib import Path

import pytest

from app.features.diagnostics.archive import ABSENT, FetchResult
from app.features.diagnostics.mpas_analysis import (
    case_name,
    is_run_url,
    parse_gallery,
    read_catalog,
    split_description,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "diagnostics"
LCRC = "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output"
RUN = (
    f"{LCRC}/diagnostics_archive/production/v3.LR/v3.LR.historical_0101"
    "/mpas_analysis/ts_1850-2014_climo_1985-2014/"
)
CRYO = f"{LCRC}/ac.dcomeau/20220526.CRYO1850.ne30pg2_ECwISC30to60E2r1.chrysalis.Kappa/yrs1-10/"
CRYO_CASE = "ECwISC30to60E2r1.CRYO1850.N2dependentDefaultKappa"


def fixture(name: str) -> str:
    return (FIXTURES / f"mpas_analysis_{name}.html").read_text()


def site(pages: dict[str, str]):
    def fetch(url: str, _remaining: float = 30.0) -> FetchResult:
        return FetchResult(body=pages[url]) if url in pages else ABSENT

    return fetch


@pytest.mark.parametrize(
    "url,label,expected",
    [
        (RUN, "", "v3.LR.historical_0101"),
        ("https://h.test/my_case_yrs21-30/html/", "", "my_case"),
        ("https://h.test/my_case/html/", "", "my_case"),
        ("https://h.test/my_case/yrs1-10/", "", "my_case"),
        ("https://h.test/my_case/yrs1-10/", "!real.case yrs 1-10", "real.case"),
        ("https://h.test/my_case/yrs1-10/", "!yrs1-10", "my_case"),
        ("https://h.test/somewhere/else/", "", None),
    ],
)
def test_case_name(url, label, expected):
    assert case_name(url, label) == expected


@pytest.mark.parametrize("url", [RUN, CRYO, "https://h.test/c_yrs1-5/html/"])
def test_is_run_url(url):
    assert is_run_url(url)


def test_e3sm_diags_viewer_is_not_an_mpas_run():
    assert not is_run_url(f"{LCRC}/x/e3sm_diags/a/model_vs_obs_1985-2014/viewer/")


def test_parse_ocean_gallery():
    plots = parse_gallery(fixture("ocean_index"), "ocean", "v3.LR.historical_0101")

    assert len(plots) == 15
    first = plots[0]
    assert (
        first.path
        == "ocean/mldHolteTalleyARGO_v3.LR.historical_0101_JFM_years1985-2014.png"
    )
    assert first.key == "ocean/Observations: Holte-Talley ARGO/mldHolteTalleyARGO_JFM"
    assert first.title == "Mean Mixed-Layer Depth"
    assert (first.season, first.region) == ("JFM", None)
    # The JFM, JAS and ANN maps of one field share a row.
    assert len({p.group for p in plots[:3]}) == 1


def test_parse_sea_ice_gallery_uses_two_letter_seasons():
    plots = parse_gallery(fixture("sea_ice_index"), "sea_ice", "v3.LR.historical_0101")
    assert len(plots) == 15
    assert {"FM", "ON"} <= {p.season for p in plots}


def test_same_plot_has_the_same_key_in_another_case():
    html = fixture("ocean_index")
    first = parse_gallery(html, "ocean", "v3.LR.historical_0101")[0]
    other = parse_gallery(
        html.replace("v3.LR.historical_0101", "v3.LR.piControl").replace(
            "1985-2014", "0001-0050"
        ),
        "ocean",
        "v3.LR.piControl",
    )[0]
    assert first.key == other.key


def test_regional_plots_are_regions_not_seasons():
    plots = parse_gallery(fixture("cryo_ocean_index"), "ocean", CRYO_CASE)

    climatology, shelf, deep = plots
    assert (
        climatology.key
        == "ocean/Observations: Holte-Talley ARGO/mldHolteTalleyARGO_JFM"
    )
    assert (shelf.season, shelf.region) == (None, "Eastern Ross Sea Shelf")
    assert shelf.title == "Regional mean of Volume-Mean Thermal Forcing"
    # Regions of one diagnostic share a row.
    assert shelf.group == deep.group


class TestReadCatalog:
    def test_reads_ocean_and_sea_ice(self):
        fetch = site(
            {
                RUN + "ocean/index.html": fixture("ocean_index"),
                RUN + "sea_ice/index.html": fixture("sea_ice_index"),
            }
        )
        catalog = read_catalog(RUN, fetch)

        assert catalog.error is None and catalog.tool == "mpas_analysis"
        assert [(s.name, s.title, len(s.plots)) for s in catalog.sets] == [
            ("ocean", "Ocean", 15),
            ("sea_ice", "Sea ice", 15),
        ]

    def test_reads_a_legacy_run_named_by_its_label(self):
        fetch = site({CRYO + "ocean/index.html": fixture("cryo_ocean_index")})
        catalog = read_catalog(CRYO, fetch, label=f"!{CRYO_CASE} yrs 1-10")
        assert catalog.error is None
        assert "Kappa" not in catalog.sets[0].plots[0].key

    def test_unknown_case_name_is_an_error(self):
        catalog = read_catalog(f"{LCRC}/x/mpas_analysis/unknown/", site({}))
        assert catalog.error == "case_name_unknown"

    def test_no_galleries_is_unavailable(self):
        assert read_catalog(RUN, site({})).error == "catalog_unavailable"

    def test_refuses_other_hosts(self):
        assert (
            read_catalog("https://evil.example/c/yrs1-5/", site({})).error
            == "url_not_allowed"
        )


@pytest.mark.parametrize(
    "desc,expected",
    [
        ("JFM", ("JFM", None)),
        ("FM", ("FM", None)),
        ("JAS z=-600 m", ("JAS", "z=-600 m")),
        ("Eastern Ross Sea Shelf ANN", ("ANN", "Eastern Ross Sea Shelf")),
        ("Eastern Ross Sea Shelf", (None, "Eastern Ross Sea Shelf")),
        ("", (None, None)),
    ],
)
def test_split_description(desc, expected):
    assert split_description(desc) == expected
