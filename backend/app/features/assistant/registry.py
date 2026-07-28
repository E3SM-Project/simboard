from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

CitationSource = Literal[
    "execution_field",
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
    "execution.id": CitationRegistryEntry(
        source_type="execution_field",
        label="Execution record ID",
    ),
    "execution.execution_id": CitationRegistryEntry(
        source_type="execution_field",
        label="Execution ID",
    ),
    "execution.description": CitationRegistryEntry(
        source_type="execution_field",
        label="Description",
    ),
    "execution.compset": CitationRegistryEntry(
        source_type="execution_field",
        label="Compset",
    ),
    "execution.compset_alias": CitationRegistryEntry(
        source_type="execution_field",
        label="Compset alias",
    ),
    "execution.grid_name": CitationRegistryEntry(
        source_type="execution_field",
        label="Grid name",
    ),
    "execution.grid_resolution": CitationRegistryEntry(
        source_type="execution_field",
        label="Grid resolution",
    ),
    "execution.simulation_type": CitationRegistryEntry(
        source_type="execution_field",
        label="Simulation type",
    ),
    "execution.status": CitationRegistryEntry(
        source_type="execution_field",
        label="Execution status",
    ),
    "execution.campaign": CitationRegistryEntry(
        source_type="execution_field",
        label="Campaign",
    ),
    "execution.experiment_type": CitationRegistryEntry(
        source_type="execution_field",
        label="Experiment type",
    ),
    "execution.initialization_type": CitationRegistryEntry(
        source_type="execution_field",
        label="Initialization type",
    ),
    "execution.simulation_start_date": CitationRegistryEntry(
        source_type="execution_field",
        label="Simulation start date",
    ),
    "execution.simulation_end_date": CitationRegistryEntry(
        source_type="execution_field",
        label="Simulation end date",
    ),
    "execution.run_start_date": CitationRegistryEntry(
        source_type="execution_field",
        label="Run start date",
    ),
    "execution.run_end_date": CitationRegistryEntry(
        source_type="execution_field",
        label="Run end date",
    ),
    "execution.compiler": CitationRegistryEntry(
        source_type="execution_field",
        label="Compiler",
    ),
    "execution.key_features": CitationRegistryEntry(
        source_type="execution_field",
        label="Key features",
    ),
    "execution.known_issues": CitationRegistryEntry(
        source_type="execution_field",
        label="Known issues",
    ),
    "execution.notes_markdown": CitationRegistryEntry(
        source_type="execution_field",
        label="Notes",
    ),
    "execution.git_repository_url": CitationRegistryEntry(
        source_type="execution_field",
        label="Git repository URL",
    ),
    "execution.git_branch": CitationRegistryEntry(
        source_type="execution_field",
        label="Git branch",
    ),
    "execution.git_tag": CitationRegistryEntry(
        source_type="execution_field",
        label="Git tag",
    ),
    "execution.git_commit_hash": CitationRegistryEntry(
        source_type="execution_field",
        label="Git commit hash",
    ),
    "execution.case_hash": CitationRegistryEntry(
        source_type="execution_field",
        label="Case hash",
    ),
    "execution.extra": CitationRegistryEntry(
        source_type="execution_field",
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
