from __future__ import annotations

from collections import OrderedDict

from app.features.assistant.registry import get_citation_entry
from app.features.assistant.schemas import (
    SimulationSummaryResponse,
    SummaryCitationOut,
)
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    build_simulation_snapshot,
)

DETERMINISTIC_LIMITATIONS = [
    "This summary uses only metadata already stored in SimBoard. It does not use retrieval, diagnostics interpretation, or LLM reasoning."
]
LLM_LIMITATIONS = [
    "This summary is grounded only in metadata already stored in SimBoard. It does not use retrieval or scientific interpretation beyond the provided metadata."
]
LLM_FALLBACK_CAVEAT = "This summary was generated using the deterministic fallback because the LLM path was unavailable."


class SummaryDraft:
    """Mutable collector used while assembling deterministic summary output."""

    def __init__(self) -> None:
        self.sentences: list[str] = []
        self.caveats: list[str] = []
        self.followups: list[str] = []
        self.citations: OrderedDict[str, SummaryCitationOut] = OrderedDict()

    def add_citation(self, path: str) -> None:
        entry = get_citation_entry(path)
        self.citations[path] = SummaryCitationOut(
            source_type=entry.source_type,
            path=path,
            label=entry.label,
        )


def _add_identity_and_status(
    snapshot: SimulationSnapshot,
    draft: SummaryDraft,
) -> None:
    change_count = (
        len(snapshot.simulation.run_config_deltas)
        if snapshot.simulation.run_config_deltas
        else 0
    )

    draft.add_citation("simulation.execution_id")
    draft.add_citation("case.name")
    draft.sentences.append(
        f"Simulation {snapshot.simulation.execution_id} belongs to case {snapshot.case.name}."
    )

    type_bits = [snapshot.simulation.simulation_type]
    if snapshot.case.reference_simulation_id:
        draft.add_citation("case.reference_simulation_id")

    if (
        snapshot.case.reference_simulation_id
        and snapshot.case.reference_simulation_id == snapshot.simulation.id
    ):
        type_bits.append("reference")
    else:
        type_bits.append("non-reference")
        if snapshot.simulation.run_config_deltas:
            draft.sentences.append(
                f"It is a non-reference run with {change_count} recorded "
                "configuration change(s) versus the case reference simulation."
            )
            draft.add_citation("simulation.run_config_deltas")
        else:
            draft.sentences.append(
                "It is a non-reference run, but SimBoard does not currently record "
                "any configuration deltas for it."
            )
            draft.caveats.append(
                "This non-reference simulation has no recorded configuration deltas in SimBoard metadata."
            )

    if snapshot.machine and snapshot.machine.name:
        draft.sentences.append(
            f"It is recorded as a {' '.join(type_bits)} simulation on machine "
            f"{snapshot.machine.name} with status {snapshot.simulation.status}."
        )
        draft.add_citation("machine.name")
    else:
        draft.sentences.append(
            f"It is recorded as a {' '.join(type_bits)} simulation with status "
            f"{snapshot.simulation.status}."
        )
        draft.caveats.append("Machine information is not recorded for this simulation.")

    draft.add_citation("simulation.simulation_type")
    draft.add_citation("simulation.status")


def _add_configuration(snapshot: SimulationSnapshot, draft: SummaryDraft) -> None:
    draft.sentences.append(
        f"It uses compset {snapshot.simulation.compset} ({snapshot.simulation.compset_alias}) "
        f"on grid {snapshot.simulation.grid_name} at {snapshot.simulation.grid_resolution} "
        f"resolution with {snapshot.simulation.initialization_type} initialization."
    )
    draft.add_citation("simulation.compset")
    draft.add_citation("simulation.compset_alias")
    draft.add_citation("simulation.grid_name")
    draft.add_citation("simulation.grid_resolution")
    draft.add_citation("simulation.initialization_type")


def _add_version_metadata(snapshot: SimulationSnapshot, draft: SummaryDraft) -> None:
    version_bits: list[str] = []
    if snapshot.simulation.git_tag:
        version_bits.append(f"tag {snapshot.simulation.git_tag}")
        draft.add_citation("simulation.git_tag")
    if snapshot.simulation.git_branch:
        version_bits.append(f"branch {snapshot.simulation.git_branch}")
        draft.add_citation("simulation.git_branch")
    if snapshot.simulation.git_commit_hash:
        version_bits.append(f"commit {snapshot.simulation.git_commit_hash}")
        draft.add_citation("simulation.git_commit_hash")

    if version_bits:
        draft.sentences.append(
            "Recorded version metadata includes " + ", ".join(version_bits) + "."
        )
    else:
        draft.caveats.append("Version metadata is not recorded for this simulation.")


def _add_timeline_metadata(snapshot: SimulationSnapshot, draft: SummaryDraft) -> None:
    start_date = snapshot.simulation.simulation_start_date
    end_date = snapshot.simulation.simulation_end_date

    if start_date and end_date:
        draft.sentences.append(
            f"The recorded simulation period runs from {start_date[:10]} to {end_date[:10]}."
        )
        draft.add_citation("simulation.simulation_start_date")
        draft.add_citation("simulation.simulation_end_date")
        return

    if start_date:
        draft.sentences.append(
            f"The recorded simulation period starts on {start_date[:10]}, and no end "
            "date is stored in SimBoard metadata."
        )
        draft.add_citation("simulation.simulation_start_date")
        draft.caveats.append(
            "Simulation end date is not recorded in SimBoard metadata."
        )
        return

    draft.caveats.append("Simulation start date is not recorded in SimBoard metadata.")


def _add_optional_metadata(snapshot: SimulationSnapshot, draft: SummaryDraft) -> None:
    if snapshot.simulation.campaign:
        draft.sentences.append(
            f"Campaign metadata identifies this run as {snapshot.simulation.campaign}."
        )
        draft.add_citation("simulation.campaign")
    else:
        draft.caveats.append("Campaign metadata is not recorded for this simulation.")

    if snapshot.simulation.experiment_type:
        draft.sentences.append(
            f"Experiment type metadata records {snapshot.simulation.experiment_type}."
        )
        draft.add_citation("simulation.experiment_type")
    else:
        draft.caveats.append(
            "Experiment type metadata is not recorded for this simulation."
        )

    if snapshot.simulation.description:
        draft.sentences.append(
            f"Recorded description: {snapshot.simulation.description.strip()}"
        )
        draft.add_citation("simulation.description")
    if snapshot.simulation.key_features:
        draft.sentences.append(
            f"Key features: {snapshot.simulation.key_features.strip()}"
        )
        draft.add_citation("simulation.key_features")
    if snapshot.simulation.known_issues:
        draft.sentences.append(
            f"Known issues: {snapshot.simulation.known_issues.strip()}"
        )
        draft.add_citation("simulation.known_issues")
    if snapshot.simulation.notes_markdown:
        draft.sentences.append("Additional notes are recorded for this simulation.")
        draft.add_citation("simulation.notes_markdown")


def _add_diagnostics_and_followups(
    snapshot: SimulationSnapshot,
    draft: SummaryDraft,
) -> None:
    diagnostic_links = [link for link in snapshot.links if link.kind == "diagnostic"]
    if diagnostic_links:
        draft.sentences.append(
            f"SimBoard records {len(diagnostic_links)} diagnostic link(s) for this "
            "run, but this summary does not interpret diagnostic outputs."
        )
        draft.add_citation("links[kind=diagnostic]")
        draft.followups.append(
            "Open the recorded diagnostic links to review supporting context for this run."
        )
    else:
        draft.caveats.append(
            "No diagnostic links are recorded for this simulation in SimBoard."
        )

    if snapshot.simulation.run_config_deltas:
        draft.followups.append(
            "Compare this run against the case reference simulation to review the recorded configuration deltas."
        )

    if snapshot.simulation.known_issues:
        draft.followups.append(
            "Review the recorded known issues before using this simulation as a baseline."
        )

    output_artifacts = [
        artifact for artifact in snapshot.artifacts if artifact.kind == "output"
    ]
    if output_artifacts:
        draft.add_citation("artifacts[kind=output]")
        draft.followups.append(
            "Open the recorded output artifacts if you need run outputs beyond the metadata summary."
        )

    if not draft.followups:
        draft.followups.append(
            "Review the simulation detail page metadata for additional provenance and run context."
        )


def build_simulation_summary(
    simulation_or_snapshot,
    *,
    include_fallback_caveat: bool = False,
) -> SimulationSummaryResponse:
    """Build a deterministic summary from authoritative SimBoard metadata."""

    snapshot = (
        simulation_or_snapshot
        if isinstance(simulation_or_snapshot, SimulationSnapshot)
        else build_simulation_snapshot(simulation_or_snapshot)
    )
    draft = SummaryDraft()
    draft.caveats.extend(snapshot.snapshot_caveats)
    _add_identity_and_status(snapshot, draft)
    _add_configuration(snapshot, draft)
    _add_version_metadata(snapshot, draft)
    _add_timeline_metadata(snapshot, draft)
    _add_optional_metadata(snapshot, draft)
    _add_diagnostics_and_followups(snapshot, draft)

    if include_fallback_caveat and LLM_FALLBACK_CAVEAT not in draft.caveats:
        draft.caveats.append(LLM_FALLBACK_CAVEAT)

    return SimulationSummaryResponse(
        answer=" ".join(draft.sentences),
        citations=list(draft.citations.values()),
        assumptions=[],
        caveats=draft.caveats,
        limitations=DETERMINISTIC_LIMITATIONS,
        suggested_followups=draft.followups,
        generation_mode="deterministic",
        fallback_used=False,
        generation_provider=None,
        generation_model=None,
        trace_id="00000000-0000-0000-0000-000000000000",
    )
