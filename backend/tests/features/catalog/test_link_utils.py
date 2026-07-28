from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.link_utils import merge_execution_and_case_links
from app.features.catalog.models import ExternalLink


def test_merge_execution_and_case_links_deduplicates_execution_links_first() -> None:
    duplicate_execution_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/shared",
        label="Execution duplicate",
    )
    primary_execution_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/shared",
        label="Execution primary",
    )
    case_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/case-only",
        label="Case only",
    )

    merged = merge_execution_and_case_links(
        [primary_execution_link, duplicate_execution_link],
        [case_link],
    )

    assert merged == [primary_execution_link, case_link]


def test_merge_execution_and_case_links_deduplicates_case_links() -> None:
    execution_link = ExternalLink(
        kind=ExternalLinkKind.DIAGNOSTIC,
        url="https://example.com/execution-only",
        label="Execution only",
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

    merged = merge_execution_and_case_links(
        [execution_link],
        [primary_case_link, duplicate_case_link],
    )

    assert merged == [execution_link, primary_case_link]
