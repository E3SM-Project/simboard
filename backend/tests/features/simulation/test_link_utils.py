from app.features.simulation.enums import ExternalLinkKind
from app.features.simulation.link_utils import merge_simulation_and_case_links
from app.features.simulation.models import ExternalLink


def test_merge_simulation_and_case_links_deduplicates_simulation_links_first() -> None:
    duplicate_simulation_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/shared",
        label="Simulation duplicate",
    )
    primary_simulation_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/shared",
        label="Simulation primary",
    )
    case_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/case-only",
        label="Case only",
    )

    merged = merge_simulation_and_case_links(
        [primary_simulation_link, duplicate_simulation_link],
        [case_link],
    )

    assert merged == [primary_simulation_link, case_link]


def test_merge_simulation_and_case_links_deduplicates_case_links() -> None:
    simulation_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/simulation-only",
        label="Simulation only",
    )
    primary_case_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/case-shared",
        label="Case primary",
    )
    duplicate_case_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/case-shared",
        label="Case duplicate",
    )

    merged = merge_simulation_and_case_links(
        [simulation_link],
        [primary_case_link, duplicate_case_link],
    )

    assert merged == [simulation_link, primary_case_link]
