"""Tests for linking documented v3 HPSS locations to Chrysalis cases."""

from types import SimpleNamespace

import pytest

from app.features.catalog.enums import ExternalLinkKind
from app.scripts.ingestion.v3_data import lcrc_v3_hpss_linker as linker


def _mapping(case_name: str, url: str = "https://portal.nersc.gov/archive/case"):
    return linker.HpssMapping(simulation=case_name, case_name=case_name, url=url)


def _case(name: str, links: list | None = None, machine_name: str = "chrysalis"):
    return SimpleNamespace(
        name=name,
        links=[] if links is None else links,
        machine_name=machine_name,
    )


def test_parse_hpss_mappings_extracts_and_normalizes_docs_rows() -> None:
    document = """
    <table>
      <tr><th>Simulation</th><th>Size</th><th>ESGF</th><th>Path</th><th>HPSS URL</th></tr>
      <tr>
        <td>v3.LR.piClim-histall/v3.LR.piClim-histall_0101</td><td>9</td>
        <td></td><td>/home/projects/e3sm</td>
        <td><a href="https://portal.nersc.gov/archive/histall">HPSS URL</a></td>
      </tr>
    </table>
    """

    assert linker._parse_hpss_mappings(document) == [
        linker.HpssMapping(
            simulation="v3.LR.piClim-histall/v3.LR.piClim-histall_0101",
            case_name="v3.LR.piClim-histall_0101",
            url="https://portal.nersc.gov/archive/histall",
        )
    ]


def test_parse_hpss_mappings_uses_header_names_instead_of_fixed_columns() -> None:
    document = """
    <table>
      <tr><th>HPSS URL</th><th>Simulation</th><th>Data Size</th></tr>
      <tr>
        <td><a href=" https://portal.nersc.gov/archive/rrm ">HPSS URL</a></td>
        <td>v3.NARRM.amip_0101</td><td>24.5</td>
      </tr>
    </table>
    """

    assert linker._parse_hpss_mappings(document) == [
        linker.HpssMapping(
            simulation="v3.NARRM.amip_0101",
            case_name="v3.NARRM.amip_0101",
            url="https://portal.nersc.gov/archive/rrm",
        )
    ]


def test_parse_hpss_mappings_includes_all_documented_case_entries() -> None:
    document = """
    <table>
      <tr><th>Simulation</th><th>HPSS URL</th></tr>
      <tr><td>LR_ensemble</td><td><a href="https://portal.nersc.gov/archive/lr">HPSS URL</a></td></tr>
      <tr><td>RRM_ensemble</td><td><a href="https://portal.nersc.gov/archive/rrm">HPSS URL</a></td></tr>
      <tr><td>v3.NARRM_r0125.amip_0101</td><td><a href="https://portal.nersc.gov/archive/narrm-symlink">HPSS URL</a></td></tr>
      <tr><td>v3.NARRM.amip_0101</td><td><a href="https://portal.nersc.gov/archive/narrm">HPSS URL</a></td></tr>
    </table>
    """

    assert linker._parse_hpss_mappings(document) == [
        linker.HpssMapping(
            simulation="LR_ensemble",
            case_name="LR_ensemble",
            url="https://portal.nersc.gov/archive/lr",
        ),
        linker.HpssMapping(
            simulation="RRM_ensemble",
            case_name="RRM_ensemble",
            url="https://portal.nersc.gov/archive/rrm",
        ),
        linker.HpssMapping(
            simulation="v3.NARRM_r0125.amip_0101",
            case_name="v3.NARRM_r0125.amip_0101",
            url="https://portal.nersc.gov/archive/narrm-symlink",
        ),
        linker.HpssMapping(
            simulation="v3.NARRM.amip_0101",
            case_name="v3.NARRM.amip_0101",
            url="https://portal.nersc.gov/archive/narrm",
        ),
    ]


def test_parse_hpss_mappings_rejects_missing_required_headers() -> None:
    with pytest.raises(ValueError, match="missing Simulation and HPSS URL headers"):
        linker._parse_hpss_mappings("<table><tr><th>Case</th></tr></table>")


def test_mapping_by_case_name_rejects_conflicting_urls() -> None:
    with pytest.raises(ValueError, match="Conflicting HPSS URLs"):
        linker._mapping_by_case_name(
            [
                _mapping("case", "https://example.org/one"),
                _mapping("case", "https://example.org/two"),
            ]
        )


def test_documented_case_names_without_match_reports_unlinked_docs_cases() -> None:
    cases = [_case("v3.LR.piControl")]
    mappings = [_mapping("v3.LR.piControl"), _mapping("v3.NARRM.amip_0101")]

    assert linker._documented_case_names_without_match(cases, mappings) == {
        "v3.NARRM.amip_0101"
    }


def test_linker_imports_models_required_by_catalog_relationships() -> None:
    assert linker.User.__name__ == "User"
    assert linker.Ingestion.__name__ == "Ingestion"
    assert linker.Site.__name__ == "Site"


def test_reconcile_cases_dry_run_does_not_mutate() -> None:
    case = _case("v3.NARRM.amip_0101")

    summary = linker.reconcile_cases([case], [_mapping(case.name)], apply=False)

    assert summary == {
        "documented_cases": 1,
        "documented_case_names": ["v3.NARRM.amip_0101"],
        "matched_cases": 1,
        "matched_case_names": ["v3.NARRM.amip_0101"],
        "links_to_create": 1,
        "documented_cases_without_match": 0,
        "documented_cases_without_match_names": [],
        "ignored_documented_cases_without_match": 0,
        "ignored_documented_cases_without_match_names": [],
        "ignored_documented_cases_without_match_issue_urls": [],
        "documented_cases_with_multiple_matches": 0,
        "documented_cases_with_multiple_matches_names": [],
        "matched_cases_chrysalis": 1,
        "matched_cases_chrysalis_names": ["v3.NARRM.amip_0101"],
    }
    assert case.links == []


def test_reconcile_cases_reports_perlmutter_matches() -> None:
    case = _case("v3.LR.amip_bonus_0101", machine_name="perlmutter")

    summary = linker.reconcile_cases([case], [_mapping(case.name)], apply=False)

    assert summary["matched_cases"] == 1
    assert summary["matched_cases_perlmutter"] == 1
    assert summary["matched_case_names"] == ["v3.LR.amip_bonus_0101"]
    assert summary["matched_cases_perlmutter_names"] == ["v3.LR.amip_bonus_0101"]


def test_reconcile_cases_reports_names_for_missing_and_duplicate_matches() -> None:
    cases = [
        _case("v3.LR.amip_0101"),
        _case("v3.LR.amip_0101", machine_name="perlmutter"),
    ]
    mappings = [
        _mapping("v3.LR.amip_0101"),
        _mapping("LR_ensemble"),
        _mapping("v3.NARRM.amip_0101"),
    ]

    summary = linker.reconcile_cases(cases, mappings, apply=False)

    assert summary["documented_case_names"] == [
        "LR_ensemble",
        "v3.LR.amip_0101",
        "v3.NARRM.amip_0101",
    ]
    assert summary["documented_cases_without_match_names"] == ["v3.NARRM.amip_0101"]
    assert summary["ignored_documented_cases_without_match"] == 1
    assert summary["ignored_documented_cases_without_match_names"] == ["LR_ensemble"]
    assert summary["ignored_documented_cases_without_match_issue_urls"] == [
        "https://github.com/E3SM-Project/simboard/issues/323"
    ]
    assert summary["documented_cases_with_multiple_matches_names"] == [
        "v3.LR.amip_0101"
    ]
    assert summary["matched_case_names"] == [
        "v3.LR.amip_0101",
        "v3.LR.amip_0101",
    ]
    assert summary["matched_cases_chrysalis_names"] == ["v3.LR.amip_0101"]
    assert summary["matched_cases_perlmutter_names"] == ["v3.LR.amip_0101"]


def test_reconcile_cases_creates_and_preserves_managed_link() -> None:
    case = _case("v3.LR.piControl")
    mapping = _mapping(case.name)

    created = linker.reconcile_cases([case], [mapping], apply=True)

    assert created["links_to_create"] == 1
    assert len(case.links) == 1
    assert case.links[0].kind == ExternalLinkKind.OTHER
    assert case.links[0].label == linker.LONG_TERM_ARCHIVE_LABEL
    assert case.links[0].url == mapping.url

    unchanged = linker.reconcile_cases([case], [mapping], apply=True)
    assert unchanged["unchanged_links"] == 1


def test_reconcile_cases_updates_only_the_managed_link() -> None:
    managed_link = SimpleNamespace(
        kind=ExternalLinkKind.OTHER,
        label=linker.LONG_TERM_ARCHIVE_LABEL,
        url="https://portal.nersc.gov/archive/old",
    )
    other_link = SimpleNamespace(
        kind=ExternalLinkKind.OTHER,
        label="Related resource",
        url="https://example.org/related",
    )
    case = _case("v3.EARRM.amip_0101", [managed_link, other_link])
    mapping = _mapping(case.name, "https://portal.nersc.gov/archive/new")

    summary = linker.reconcile_cases([case], [mapping], apply=True)

    assert summary["links_to_update"] == 1
    assert managed_link.url == mapping.url
    assert other_link.url == "https://example.org/related"


def test_reconcile_cases_reports_ambiguous_managed_links() -> None:
    managed_links = [
        SimpleNamespace(
            kind=ExternalLinkKind.OTHER,
            label=linker.LONG_TERM_ARCHIVE_LABEL,
            url=f"https://portal.nersc.gov/archive/{suffix}",
        )
        for suffix in ("one", "two")
    ]
    case = _case("v3.AMZRRM.amip_0101", managed_links)

    summary = linker.reconcile_cases([case], [_mapping(case.name)], apply=True)

    assert summary["ambiguous_cases"] == 1
    assert [link.url for link in managed_links] == [
        "https://portal.nersc.gov/archive/one",
        "https://portal.nersc.gov/archive/two",
    ]


def test_reconcile_cases_does_not_duplicate_an_existing_other_link_url() -> None:
    existing_link = SimpleNamespace(
        kind=ExternalLinkKind.OTHER,
        label="Existing archive reference",
        url="https://portal.nersc.gov/archive/case",
    )
    case = _case("v3.LR.amip_0101", [existing_link])

    summary = linker.reconcile_cases([case], [_mapping(case.name)], apply=True)

    assert summary["conflicting_existing_urls"] == 1
    assert existing_link.label == "Existing archive reference"


def test_reconcile_cases_does_not_update_to_an_existing_other_link_url() -> None:
    managed_link = SimpleNamespace(
        kind=ExternalLinkKind.OTHER,
        label=linker.LONG_TERM_ARCHIVE_LABEL,
        url="https://portal.nersc.gov/archive/old",
    )
    existing_link = SimpleNamespace(
        kind=ExternalLinkKind.OTHER,
        label="Existing archive reference",
        url="https://portal.nersc.gov/archive/new",
    )
    case = _case("v3.LR.amip_0151", [managed_link, existing_link])

    summary = linker.reconcile_cases(
        [case], [_mapping(case.name, existing_link.url)], apply=True
    )

    assert summary["conflicting_existing_urls"] == 1
    assert managed_link.url == "https://portal.nersc.gov/archive/old"
