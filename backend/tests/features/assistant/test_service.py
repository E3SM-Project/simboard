from uuid import UUID

from sqlalchemy.orm import Session

from app.features.assistant.service import build_simulation_summary
from app.features.assistant.snapshot import (
    SimulationSnapshot,
    SnapshotCaseFields,
    SnapshotSimulationFields,
)
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.enums import ArtifactKind, ExternalLinkKind
from app.features.simulation.models import Artifact, Case, ExternalLink, Simulation


def _create_case(db: Session, name: str = "assistant_case") -> Case:
    machine = db.query(Machine).first()
    assert machine is not None

    case = Case(name=name, machine_id=machine.id, hpc_username="assistant-user")
    db.add(case)
    db.flush()
    return case


def _create_simulation(
    db: Session,
    normal_user_sync: dict[str, UUID | str],
    admin_user_sync: dict[str, UUID | str],
    *,
    case_name: str = "assistant_case",
    execution_id: str = "assistant-exec-1",
    case_hash: str | None = "assistant-hash-1",
    with_diagnostics: bool = True,
    with_optional_metadata: bool = True,
) -> Simulation:
    machine = db.query(Machine).first()
    assert machine is not None

    case = _create_case(db, case_name)

    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference=execution_id,
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
    )
    db.add(ingestion)
    db.flush()

    simulation = Simulation(
        case_id=case.id,
        execution_id=execution_id,
        description="Control simulation for deterministic summary."
        if with_optional_metadata
        else None,
        compset="AQUAPLANET",
        compset_alias="QPC4",
        grid_name="f19_f19",
        grid_resolution="1.9x2.5",
        simulation_type="experimental",
        status="completed",
        campaign="historical" if with_optional_metadata else None,
        experiment_type="historical" if with_optional_metadata else None,
        initialization_type="startup",
        simulation_start_date="2023-01-01T00:00:00Z",
        simulation_end_date="2023-12-31T00:00:00Z" if with_optional_metadata else None,
        compiler="gcc",
        key_features="High-resolution control setup."
        if with_optional_metadata
        else None,
        known_issues="Sea-ice diagnostics pending QA."
        if with_optional_metadata
        else None,
        notes_markdown="Reviewed by domain team." if with_optional_metadata else None,
        git_branch="main" if with_optional_metadata else None,
        git_tag="v1.2.3" if with_optional_metadata else None,
        git_commit_hash="abc123def456" if with_optional_metadata else None,
        case_hash=case_hash,
        created_by=normal_user_sync["id"],
        last_updated_by=admin_user_sync["id"],
        ingestion_id=ingestion.id,
    )
    db.add(simulation)
    db.flush()

    if with_diagnostics:
        db.add(
            ExternalLink(
                simulation_id=simulation.id,
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/diag",
                label="Diagnostics Dashboard",
            )
        )

    db.add(
        Artifact(
            simulation_id=simulation.id,
            kind=ArtifactKind.OUTPUT,
            uri="/archive/output.nc",
            label="Primary output",
        )
    )

    db.commit()
    db.refresh(simulation)
    return simulation


class TestBuildSimulationSummary:
    def test_complete_metadata_produces_stable_summary_and_citations(
        self, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(
            db,
            normal_user_sync,
            admin_user_sync,
            execution_id="assistant-complete",
        )

        summary = build_simulation_summary(simulation)

        assert (
            "Simulation assistant-complete belongs to case assistant_case."
            in summary.answer
        )
        assert (
            "Recorded version metadata includes tag v1.2.3, branch main, commit abc123def456."
            in summary.answer
        )
        assert "SimBoard records 1 diagnostic link(s) for this run" in summary.answer
        assert {citation.path for citation in summary.citations} >= {
            "simulation.execution_id",
            "case.name",
            "simulation.git_tag",
            "links[kind=diagnostic]",
        }

    def test_missing_optional_metadata_yields_caveats_not_fabrication(
        self, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(
            db,
            normal_user_sync,
            admin_user_sync,
            execution_id="assistant-missing",
            with_diagnostics=False,
            with_optional_metadata=False,
        )

        summary = build_simulation_summary(simulation)

        assert "Recorded description:" not in summary.answer
        assert (
            "Version metadata is not recorded for this simulation." in summary.caveats
        )
        assert (
            "Campaign metadata is not recorded for this simulation." in summary.caveats
        )
        assert (
            "No diagnostic links are recorded for this simulation in SimBoard."
            in summary.caveats
        )

    def test_case_hash_grouping_is_reflected_in_summary(
        self, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(
            db,
            normal_user_sync,
            admin_user_sync,
            execution_id="assistant-grouped",
            case_hash="assistant-grouped-hash",
        )

        summary = build_simulation_summary(simulation)

        assert (
            "It is grouped under CASE_HASH assistant-grouped-hash within this case."
            in summary.answer
        )
        assert "simulation.case_hash" in {
            citation.path for citation in summary.citations
        }

    def test_absent_diagnostics_adds_limitation_not_interpretation(
        self, db: Session, normal_user_sync, admin_user_sync
    ) -> None:
        simulation = _create_simulation(
            db,
            normal_user_sync,
            admin_user_sync,
            execution_id="assistant-nodiag",
            with_diagnostics=False,
        )

        summary = build_simulation_summary(simulation)

        assert "interpret diagnostic outputs" not in summary.answer
        assert (
            "No diagnostic links are recorded for this simulation in SimBoard."
            in summary.caveats
        )
        assert summary.limitations == [
            "This summary uses only metadata already stored in SimBoard. It does not use retrieval, diagnostics interpretation, or LLM reasoning."
        ]

    def test_snapshot_without_case_hash_omits_grouping_sentence(self) -> None:
        summary = build_simulation_summary(
            SimulationSnapshot(
                simulation=SnapshotSimulationFields(
                    id="simulation-1",
                    execution_id="assistant-no-case-hash",
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    simulation_type="experimental",
                    status="completed",
                    initialization_type="startup",
                    simulation_start_date="2023-01-01T00:00:00Z",
                ),
                case=SnapshotCaseFields(name="assistant_case"),
            )
        )

        assert "CASE_HASH" not in summary.answer

    def test_missing_start_date_adds_caveat_and_default_followup(self) -> None:
        summary = build_simulation_summary(
            SimulationSnapshot(
                simulation=SnapshotSimulationFields(
                    id="simulation-1",
                    execution_id="assistant-no-start-date",
                    compset="AQUAPLANET",
                    compset_alias="QPC4",
                    grid_name="f19_f19",
                    grid_resolution="1.9x2.5",
                    simulation_type="experimental",
                    status="completed",
                    initialization_type="startup",
                ),
                case=SnapshotCaseFields(name="assistant_case"),
            )
        )

        assert (
            "Simulation start date is not recorded in SimBoard metadata."
            in summary.caveats
        )
        assert summary.suggested_followups == [
            "Review the simulation detail page metadata for additional provenance and run context."
        ]
