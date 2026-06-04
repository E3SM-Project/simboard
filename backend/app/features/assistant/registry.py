from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

CitationSource = Literal[
    "simulation_field",
    "case_field",
    "machine_field",
    "artifact",
    "external_link",
]


@dataclass(frozen=True)
class CitationRegistryEntry:
    source_type: CitationSource
    label: str


_CITATION_REGISTRY = {
    "simulation.id": CitationRegistryEntry(
        source_type="simulation_field",
        label="Simulation ID",
    ),
    "simulation.execution_id": CitationRegistryEntry(
        source_type="simulation_field",
        label="Execution ID",
    ),
    "simulation.description": CitationRegistryEntry(
        source_type="simulation_field",
        label="Description",
    ),
    "simulation.compset": CitationRegistryEntry(
        source_type="simulation_field",
        label="Compset",
    ),
    "simulation.compset_alias": CitationRegistryEntry(
        source_type="simulation_field",
        label="Compset alias",
    ),
    "simulation.grid_name": CitationRegistryEntry(
        source_type="simulation_field",
        label="Grid name",
    ),
    "simulation.grid_resolution": CitationRegistryEntry(
        source_type="simulation_field",
        label="Grid resolution",
    ),
    "simulation.simulation_type": CitationRegistryEntry(
        source_type="simulation_field",
        label="Simulation type",
    ),
    "simulation.status": CitationRegistryEntry(
        source_type="simulation_field",
        label="Simulation status",
    ),
    "simulation.campaign": CitationRegistryEntry(
        source_type="simulation_field",
        label="Campaign",
    ),
    "simulation.experiment_type": CitationRegistryEntry(
        source_type="simulation_field",
        label="Experiment type",
    ),
    "simulation.initialization_type": CitationRegistryEntry(
        source_type="simulation_field",
        label="Initialization type",
    ),
    "simulation.simulation_start_date": CitationRegistryEntry(
        source_type="simulation_field",
        label="Simulation start date",
    ),
    "simulation.simulation_end_date": CitationRegistryEntry(
        source_type="simulation_field",
        label="Simulation end date",
    ),
    "simulation.run_start_date": CitationRegistryEntry(
        source_type="simulation_field",
        label="Run start date",
    ),
    "simulation.run_end_date": CitationRegistryEntry(
        source_type="simulation_field",
        label="Run end date",
    ),
    "simulation.compiler": CitationRegistryEntry(
        source_type="simulation_field",
        label="Compiler",
    ),
    "simulation.key_features": CitationRegistryEntry(
        source_type="simulation_field",
        label="Key features",
    ),
    "simulation.known_issues": CitationRegistryEntry(
        source_type="simulation_field",
        label="Known issues",
    ),
    "simulation.notes_markdown": CitationRegistryEntry(
        source_type="simulation_field",
        label="Notes",
    ),
    "simulation.git_repository_url": CitationRegistryEntry(
        source_type="simulation_field",
        label="Git repository URL",
    ),
    "simulation.git_branch": CitationRegistryEntry(
        source_type="simulation_field",
        label="Git branch",
    ),
    "simulation.git_tag": CitationRegistryEntry(
        source_type="simulation_field",
        label="Git tag",
    ),
    "simulation.git_commit_hash": CitationRegistryEntry(
        source_type="simulation_field",
        label="Git commit hash",
    ),
    "simulation.case_hash": CitationRegistryEntry(
        source_type="simulation_field",
        label="Case hash",
    ),
    "simulation.extra": CitationRegistryEntry(
        source_type="simulation_field",
        label="Extra metadata",
    ),
    "case.name": CitationRegistryEntry(
        source_type="case_field",
        label="Case name",
    ),
    "case.case_group": CitationRegistryEntry(
        source_type="case_field",
        label="Case group",
    ),
    "machine.name": CitationRegistryEntry(
        source_type="machine_field",
        label="Machine name",
    ),
    "artifacts[kind=output]": CitationRegistryEntry(
        source_type="artifact",
        label="Output artifacts",
    ),
    "artifacts[kind=archive]": CitationRegistryEntry(
        source_type="artifact",
        label="Archive artifacts",
    ),
    "artifacts[kind=run_script]": CitationRegistryEntry(
        source_type="artifact",
        label="Run script artifacts",
    ),
    "artifacts[kind=postprocessing_script]": CitationRegistryEntry(
        source_type="artifact",
        label="Postprocessing script artifacts",
    ),
    "links[kind=diagnostic]": CitationRegistryEntry(
        source_type="external_link",
        label="Diagnostic links",
    ),
    "links[kind=performance]": CitationRegistryEntry(
        source_type="external_link",
        label="Performance links",
    ),
    "links[kind=docs]": CitationRegistryEntry(
        source_type="external_link",
        label="Documentation links",
    ),
    "links[kind=other]": CitationRegistryEntry(
        source_type="external_link",
        label="Other links",
    ),
}

CITATION_REGISTRY = MappingProxyType(_CITATION_REGISTRY)
VALID_CITATION_PATHS = frozenset(CITATION_REGISTRY)


def get_citation_entry(path: str) -> CitationRegistryEntry:
    return CITATION_REGISTRY[path]
