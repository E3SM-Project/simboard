from __future__ import annotations

from collections.abc import Iterable

from app.features.simulation.models import ExternalLink


def merge_simulation_and_case_links(
    simulation_links: Iterable[ExternalLink],
    case_links: Iterable[ExternalLink],
) -> list[ExternalLink]:
    """Merge simulation-owned and case-owned links with simulation precedence."""
    merged: list[ExternalLink] = []
    seen: set[tuple[str, str]] = set()

    for link in simulation_links:
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
