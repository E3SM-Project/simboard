from __future__ import annotations

from collections.abc import Iterable

from app.features.catalog.models import ExternalLink


def merge_execution_and_case_links(
    execution_links: Iterable[ExternalLink],
    case_links: Iterable[ExternalLink],
) -> list[ExternalLink]:
    """Merge execution-owned and case-owned links with execution precedence."""
    merged: list[ExternalLink] = []
    seen: set[tuple[str, str]] = set()

    for link in execution_links:
        key = (str(link.kind), link.url)
        if key in seen:
            continue
        seen.add(key)
        merged.append(link)

    for link in case_links:
        key = (str(link.kind), link.url)
        if key in seen:
            continue
        seen.add(key)
        merged.append(link)

    return merged
