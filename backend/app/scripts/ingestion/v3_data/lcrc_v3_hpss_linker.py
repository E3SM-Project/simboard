"""Link documented E3SM v3 HPSS locations to existing Chrysalis cases."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.models import Case, ExternalLink
from app.features.ingestion.models import Ingestion  # noqa: F401
from app.features.machine.models import Machine
from app.features.site.models import Site  # noqa: F401
from app.features.user.models import User  # noqa: F401

V3_SIMULATION_TABLE_URL = (
    "https://docs.e3sm.org/e3sm_data_docs/_build/html/v3/"
    "CoupledSystem/simulation_data/simulation_table.html"
)
CHRYSALIS_MACHINE_NAME = "chrysalis"
PERLMUTTER_MACHINE_NAME = "perlmutter"
LINKABLE_MACHINE_NAMES = frozenset({CHRYSALIS_MACHINE_NAME, PERLMUTTER_MACHINE_NAME})
LONG_TERM_ARCHIVE_LABEL = "Long-Term Archive"
ReconciliationSummary = dict[str, int | list[str]]


@dataclass(frozen=True)
class HpssMapping:
    """One normalized documented simulation and its public HPSS URL."""

    simulation: str
    case_name: str
    url: str


class _SimulationTableParser(HTMLParser):
    """Extract table cells and hyperlinks without depending on an HTML package."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, list[str]]]] = []
        self._row: list[tuple[str, list[str]]] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_links: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
            self._cell_links = []
        elif tag == "a" and self._cell_links is not None:
            href = dict(attrs).get("href")
            if href:
                self._cell_links.append(href)

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if (
            tag in {"td", "th"}
            and self._cell_parts is not None
            and self._row is not None
        ):
            self._row.append(
                ("".join(self._cell_parts).strip(), self._cell_links or [])
            )
            self._cell_parts = None
            self._cell_links = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write link changes.")
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Read saved simulation-table HTML instead of downloading it.",
    )
    args = parser.parse_args(argv)
    try:
        summary = _run(apply=args.apply, source_file=args.source_file)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"HPSS link reconciliation failed: {exc}", file=sys.stderr)
        return 1

    print(f"mode={'apply' if args.apply else 'dry-run'}")
    for name, value in sorted(summary.items()):
        print(f"{name}={value}")
    return 0


def _run(*, apply: bool, source_file: Path | None = None) -> ReconciliationSummary:
    """Run a dry-run or write-mode reconciliation against linkable v3 cases."""
    mappings = _parse_hpss_mappings(_read_document(source_file))
    if not mappings:
        raise ValueError(
            "No Simulation-to-HPSS mappings were found in the source table."
        )

    with SessionLocal() as db:
        cases = list(
            db.scalars(
                select(Case)
                .join(Machine)
                .where(Machine.name.in_(LINKABLE_MACHINE_NAMES))
                .options(selectinload(Case.links), selectinload(Case.machine))
            )
        )
        missing_case_names = _documented_case_names_without_match(cases, mappings)

        if apply and missing_case_names:
            sample = ", ".join(sorted(missing_case_names)[:5])
            raise ValueError(
                "Refusing to apply HPSS links because documented cases are missing "
                f"from linkable machines: {sample}"
            )

        summary = reconcile_cases(cases, mappings, apply=apply)

        if apply:
            db.commit()

        return summary


def _read_document(source_file: Path | None) -> str:
    if source_file is not None:
        return source_file.read_text(encoding="utf-8")

    with urllib.request.urlopen(V3_SIMULATION_TABLE_URL, timeout=30) as response:
        return response.read().decode("utf-8")


def _parse_hpss_mappings(document: str) -> list[HpssMapping]:
    """Parse the documentation table's Simulation and HPSS URL columns."""
    parser = _SimulationTableParser()
    parser.feed(document)
    mappings: list[HpssMapping] = []
    header: list[tuple[str, list[str]]] | None = None

    for row in parser.rows:
        column_names = [cell[0].strip().casefold() for cell in row]

        if "simulation" in column_names and "hpss url" in column_names:
            header = row
            continue

        if header is None:
            continue

        simulation_index = next(
            index
            for index, cell in enumerate(header)
            if cell[0].strip().casefold() == "simulation"
        )

        hpss_url_index = next(
            index
            for index, cell in enumerate(header)
            if cell[0].strip().casefold() == "hpss url"
        )

        if len(row) <= max(simulation_index, hpss_url_index):
            raise ValueError("Simulation table row is missing a required column.")

        simulation = row[simulation_index][0]
        hpss_urls = [url.strip() for url in row[hpss_url_index][1]]

        if not simulation or not hpss_urls:
            continue

        url = hpss_urls[0]
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError(f"Invalid HPSS URL for simulation {simulation!r}.")

        mappings.append(
            HpssMapping(
                simulation=simulation,
                case_name=_normalize_case_name(simulation),
                url=url,
            )
        )

    if header is None:
        raise ValueError("Simulation table is missing Simulation and HPSS URL headers.")

    return mappings


def _normalize_case_name(simulation: str) -> str:
    """Convert a docs Simulation value to its archive case-directory leaf name."""
    return simulation.strip().rstrip("/").rsplit("/", maxsplit=1)[-1]


def reconcile_cases(
    cases: list[Case], mappings: list[HpssMapping], *, apply: bool
) -> ReconciliationSummary:
    """Reconcile managed long-term archive links for the supplied cases."""
    mappings_by_case = _mapping_by_case_name(mappings)
    summary: Counter[str] = Counter(documented_cases=len(mappings_by_case))
    matched_case_names: set[str] = set()
    matched_case_counts: Counter[str] = Counter()
    matched_case_names_by_machine: defaultdict[str, list[str]] = defaultdict(list)

    for case in cases:
        machine_name = _case_machine_name(case)
        mapping = mappings_by_case.get(case.name)
        if mapping is None:
            summary["cases_without_mapping"] += 1
            summary[f"cases_without_mapping_{machine_name}"] += 1
            continue

        summary["matched_cases"] += 1
        summary[f"matched_cases_{machine_name}"] += 1
        matched_case_names.add(case.name)
        matched_case_counts[case.name] += 1
        matched_case_names_by_machine[machine_name].append(case.name)
        managed_links = [
            link
            for link in case.links
            if link.kind == ExternalLinkKind.OTHER
            and link.label == LONG_TERM_ARCHIVE_LABEL
        ]

        if len(managed_links) > 1:
            summary["ambiguous_cases"] += 1
            continue

        if not managed_links:
            if any(
                link.kind == ExternalLinkKind.OTHER and link.url == mapping.url
                for link in case.links
            ):
                summary["conflicting_existing_urls"] += 1
                continue

            summary["links_to_create"] += 1

            if apply:
                case.links.append(
                    ExternalLink(
                        kind=ExternalLinkKind.OTHER,
                        label=LONG_TERM_ARCHIVE_LABEL,
                        url=mapping.url,
                    )
                )

            continue

        link = managed_links[0]

        if link.url == mapping.url:
            summary["unchanged_links"] += 1
        else:
            if any(
                other_link is not link
                and other_link.kind == ExternalLinkKind.OTHER
                and other_link.url == mapping.url
                for other_link in case.links
            ):
                summary["conflicting_existing_urls"] += 1

                continue
            summary["links_to_update"] += 1

            if apply:
                link.url = mapping.url

    summary["documented_cases_without_match"] = len(
        set(mappings_by_case) - matched_case_names
    )
    summary["documented_cases_with_multiple_matches"] = sum(
        count > 1 for count in matched_case_counts.values()
    )

    return {
        **summary,
        "documented_case_names": sorted(mappings_by_case),
        "documented_cases_without_match_names": sorted(
            set(mappings_by_case) - matched_case_names
        ),
        "documented_cases_with_multiple_matches_names": sorted(
            case_name for case_name, count in matched_case_counts.items() if count > 1
        ),
        "matched_case_names": sorted(
            case_name
            for case_names in matched_case_names_by_machine.values()
            for case_name in case_names
        ),
        **{
            f"matched_cases_{machine_name}_names": sorted(case_names)
            for machine_name, case_names in matched_case_names_by_machine.items()
        },
    }


def _case_machine_name(case: Case) -> str:
    """Return the loaded machine name, including lightweight test doubles."""
    machine_name = getattr(case, "machine_name", None)
    if isinstance(machine_name, str):
        return machine_name
    return case.machine.name


def _mapping_by_case_name(mappings: list[HpssMapping]) -> dict[str, HpssMapping]:
    """Validate that every normalized case name maps to one HPSS URL."""
    by_case_name: dict[str, HpssMapping] = {}
    for mapping in mappings:
        existing = by_case_name.get(mapping.case_name)

        if existing is not None and existing.url != mapping.url:
            raise ValueError(
                f"Conflicting HPSS URLs for normalized case {mapping.case_name!r}."
            )

        by_case_name[mapping.case_name] = mapping

    return by_case_name


def _documented_case_names_without_match(
    cases: list[Case], mappings: list[HpssMapping]
) -> set[str]:
    """Return documented cases not present in the loaded linkable case set."""
    return set(_mapping_by_case_name(mappings)) - {case.name for case in cases}


if __name__ == "__main__":
    raise SystemExit(main())
