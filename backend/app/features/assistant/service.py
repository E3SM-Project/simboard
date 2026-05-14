from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Literal

from app.features.assistant.schemas import SimulationSummaryResponse, SummaryCitationOut
from app.features.simulation.enums import ArtifactKind, ExternalLinkKind
from app.features.simulation.models import Simulation

CitationSource = Literal[
    "simulation_field",
    "case_field",
    "machine_field",
    "artifact",
    "external_link",
]

LIMITATIONS = [
    "This v1 summary uses only metadata already stored in SimBoard. It does not use retrieval, diagnostics interpretation, or LLM reasoning."
]


class SummaryDraft:
    """Mutable collector used while assembling deterministic summary output."""

    def __init__(self) -> None:
        self.sentences: list[str] = []
        self.caveats: list[str] = []
        self.followups: list[str] = []
        self.citations: OrderedDict[tuple[str, str], SummaryCitationOut] = OrderedDict()

    def add_citation(self, source_type: CitationSource, path: str, label: str) -> None:
        self.citations[(source_type, path)] = SummaryCitationOut(
            source_type=source_type,
            path=path,
            label=label,
        )


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.date().isoformat()


def _add_identity_and_status(simulation: Simulation, draft: SummaryDraft) -> None:
    case = simulation.case
    machine = simulation.machine
    is_reference = case.reference_simulation_id == simulation.id
    change_count = (
        len(simulation.run_config_deltas) if simulation.run_config_deltas else 0
    )

    draft.add_citation("simulation_field", "simulation.execution_id", "Execution ID")
    draft.add_citation("case_field", "case.name", "Case name")
    draft.sentences.append(
        f"Simulation {simulation.execution_id} belongs to case {case.name}."
    )

    type_bits = [_enum_value(simulation.simulation_type)]
    if is_reference:
        type_bits.append("reference")
        draft.add_citation(
            "case_field",
            "case.reference_simulation_id",
            "Reference simulation",
        )
    else:
        type_bits.append("non-reference")
        if simulation.run_config_deltas:
            draft.sentences.append(
                f"It is a non-reference run with {change_count} recorded "
                "configuration change(s) versus the case reference simulation."
            )
            draft.add_citation(
                "simulation_field",
                "simulation.run_config_deltas",
                "Configuration deltas",
            )
        else:
            draft.sentences.append(
                "It is a non-reference run, but SimBoard does not currently record "
                "any configuration deltas for it."
            )
            draft.caveats.append(
                "This non-reference simulation has no recorded configuration deltas "
                "in SimBoard metadata."
            )

    if machine is not None and machine.name:
        draft.sentences.append(
            f"It is recorded as a {' '.join(type_bits)} simulation on machine "
            f"{machine.name} with status {_enum_value(simulation.status)}."
        )
        draft.add_citation("machine_field", "machine.name", "Machine name")
    else:
        draft.sentences.append(
            f"It is recorded as a {' '.join(type_bits)} simulation with status "
            f"{_enum_value(simulation.status)}."
        )
        draft.caveats.append("Machine information is not recorded for this simulation.")

    draft.add_citation(
        "simulation_field", "simulation.simulation_type", "Simulation type"
    )
    draft.add_citation("simulation_field", "simulation.status", "Simulation status")


def _add_configuration(simulation: Simulation, draft: SummaryDraft) -> None:
    draft.sentences.append(
        f"It uses compset {simulation.compset} ({simulation.compset_alias}) on grid "
        f"{simulation.grid_name} at {simulation.grid_resolution} resolution with "
        f"{simulation.initialization_type} initialization."
    )
    draft.add_citation("simulation_field", "simulation.compset", "Compset")
    draft.add_citation("simulation_field", "simulation.compset_alias", "Compset alias")
    draft.add_citation("simulation_field", "simulation.grid_name", "Grid name")
    draft.add_citation(
        "simulation_field", "simulation.grid_resolution", "Grid resolution"
    )
    draft.add_citation(
        "simulation_field",
        "simulation.initialization_type",
        "Initialization type",
    )


def _add_version_metadata(simulation: Simulation, draft: SummaryDraft) -> None:
    version_bits: list[str] = []
    if simulation.git_tag:
        version_bits.append(f"tag {simulation.git_tag}")
        draft.add_citation("simulation_field", "simulation.git_tag", "Git tag")
    if simulation.git_branch:
        version_bits.append(f"branch {simulation.git_branch}")
        draft.add_citation("simulation_field", "simulation.git_branch", "Git branch")
    if simulation.git_commit_hash:
        version_bits.append(f"commit {simulation.git_commit_hash}")
        draft.add_citation(
            "simulation_field",
            "simulation.git_commit_hash",
            "Git commit hash",
        )

    if version_bits:
        draft.sentences.append(
            "Recorded version metadata includes " + ", ".join(version_bits) + "."
        )
    else:
        draft.caveats.append("Version metadata is not recorded for this simulation.")


def _add_timeline_metadata(simulation: Simulation, draft: SummaryDraft) -> None:
    start_date = _format_timestamp(simulation.simulation_start_date)
    end_date = _format_timestamp(simulation.simulation_end_date)

    if start_date and end_date:
        draft.sentences.append(
            f"The recorded simulation period runs from {start_date} to {end_date}."
        )
        draft.add_citation(
            "simulation_field",
            "simulation.simulation_start_date",
            "Simulation start date",
        )
        draft.add_citation(
            "simulation_field",
            "simulation.simulation_end_date",
            "Simulation end date",
        )
        return

    if start_date:
        draft.sentences.append(
            f"The recorded simulation period starts on {start_date}, and no end "
            "date is stored in SimBoard metadata."
        )
        draft.add_citation(
            "simulation_field",
            "simulation.simulation_start_date",
            "Simulation start date",
        )
        draft.caveats.append(
            "Simulation end date is not recorded in SimBoard metadata."
        )
        return

    draft.caveats.append("Simulation start date is not recorded in SimBoard metadata.")


def _add_optional_metadata(simulation: Simulation, draft: SummaryDraft) -> None:
    if simulation.campaign:
        draft.sentences.append(
            f"Campaign metadata identifies this run as {simulation.campaign}."
        )
        draft.add_citation("simulation_field", "simulation.campaign", "Campaign")
    else:
        draft.caveats.append("Campaign metadata is not recorded for this simulation.")

    if simulation.experiment_type:
        draft.sentences.append(
            f"Experiment type metadata records {simulation.experiment_type}."
        )
        draft.add_citation(
            "simulation_field",
            "simulation.experiment_type",
            "Experiment type",
        )
    else:
        draft.caveats.append(
            "Experiment type metadata is not recorded for this simulation."
        )

    if simulation.description:
        draft.sentences.append(
            f"Recorded description: {simulation.description.strip()}"
        )
        draft.add_citation("simulation_field", "simulation.description", "Description")
    if simulation.key_features:
        draft.sentences.append(f"Key features: {simulation.key_features.strip()}")
        draft.add_citation(
            "simulation_field", "simulation.key_features", "Key features"
        )
    if simulation.known_issues:
        draft.sentences.append(f"Known issues: {simulation.known_issues.strip()}")
        draft.add_citation(
            "simulation_field",
            "simulation.known_issues",
            "Known issues",
        )
    if simulation.notes_markdown:
        draft.sentences.append("Additional notes are recorded for this simulation.")
        draft.add_citation("simulation_field", "simulation.notes_markdown", "Notes")


def _add_diagnostics_and_followups(simulation: Simulation, draft: SummaryDraft) -> None:
    diagnostic_links = [
        link for link in simulation.links if link.kind == ExternalLinkKind.DIAGNOSTIC
    ]
    if diagnostic_links:
        draft.sentences.append(
            f"SimBoard records {len(diagnostic_links)} diagnostic link(s) for this "
            "run, but this v1 summary does not interpret diagnostic outputs."
        )
        draft.add_citation(
            "external_link",
            "links[kind=diagnostic]",
            "Diagnostic links",
        )
        draft.followups.append(
            "Open the recorded diagnostic links to review supporting context for this run."
        )
    else:
        draft.caveats.append(
            "No diagnostic links are recorded for this simulation in SimBoard."
        )

    if simulation.run_config_deltas:
        draft.followups.append(
            "Compare this run against the case reference simulation to review the "
            "recorded configuration deltas."
        )

    if simulation.known_issues:
        draft.followups.append(
            "Review the recorded known issues before using this simulation as a baseline."
        )

    output_artifacts = [
        artifact
        for artifact in simulation.artifacts
        if artifact.kind == ArtifactKind.OUTPUT
    ]
    if output_artifacts:
        draft.add_citation("artifact", "artifacts[kind=output]", "Output artifacts")
        draft.followups.append(
            "Open the recorded output artifacts if you need run outputs beyond the metadata summary."
        )

    if not draft.followups:
        draft.followups.append(
            "Review the simulation detail page metadata for additional provenance and run context."
        )


def build_simulation_summary(simulation: Simulation) -> SimulationSummaryResponse:
    """Build a deterministic summary from authoritative SimBoard metadata."""

    draft = SummaryDraft()
    _add_identity_and_status(simulation, draft)
    _add_configuration(simulation, draft)
    _add_version_metadata(simulation, draft)
    _add_timeline_metadata(simulation, draft)
    _add_optional_metadata(simulation, draft)
    _add_diagnostics_and_followups(simulation, draft)

    return SimulationSummaryResponse(
        answer=" ".join(draft.sentences),
        citations=list(draft.citations.values()),
        assumptions=[],
        caveats=draft.caveats,
        limitations=LIMITATIONS,
        suggested_followups=draft.followups,
        trace_id="00000000-0000-0000-0000-000000000000",
    )
