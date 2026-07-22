from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.features.assistant import snapshot as snapshot_module
from app.features.assistant.snapshot import (
    SNAPSHOT_TRUNCATED_CAVEAT,
    SimulationSnapshot,
    SnapshotArtifact,
    SnapshotBudgetExceededError,
    SnapshotCaseFields,
    SnapshotLink,
    SnapshotMachineFields,
    SnapshotSimulationFields,
    _SnapshotSizeBudget,
)
from app.features.simulation.enums import (
    ExternalLinkKind,
    SimulationStatus,
    SimulationType,
)
from app.features.simulation.models import Case, ExternalLink, Simulation


def _make_snapshot() -> SimulationSnapshot:
    return SimulationSnapshot(
        simulation=SnapshotSimulationFields(
            id="simulation-1",
            execution_id="assistant-snapshot-exec",
            description="Description " * 5,
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            simulation_type="experimental",
            status="completed",
            initialization_type="startup",
            notes_markdown="Notes " * 5,
            key_features="Features " * 5,
            known_issues="Issues " * 5,
            case_hash="snapshot-hash-1",
            extra={"foo": "bar"},
        ),
        case=SnapshotCaseFields(name="assistant_case"),
        machine=SnapshotMachineFields(name="perlmutter"),
        artifacts=[
            SnapshotArtifact(kind="output", uri="/output.nc", label="Output"),
            SnapshotArtifact(kind="archive", uri="/archive.tar", label="Archive"),
        ],
        links=[
            SnapshotLink(
                kind="diagnostic", url="https://example.com/diag", label="Diag"
            ),
            SnapshotLink(kind="docs", url="https://example.com/docs", label="Docs"),
            SnapshotLink(kind="other", url="https://example.com/other", label="Other"),
        ],
        snapshot_caveats=[],
    )


class TestSnapshotHelpers:
    def test_enum_value_and_isoformat_handle_none_enum_and_plain_values(self) -> None:
        timestamp = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)

        assert snapshot_module._enum_value(None) is None
        assert snapshot_module._enum_value(SimulationStatus.COMPLETED) == "completed"
        assert snapshot_module._enum_value("plain-value") == "plain-value"
        assert snapshot_module._isoformat(None) is None
        assert snapshot_module._isoformat(timestamp) == "2024-01-02T03:04:05+00:00"

    def test_add_truncation_caveat_is_idempotent(self) -> None:
        snapshot = _make_snapshot()

        updated = snapshot_module._add_truncation_caveat(snapshot)
        again = snapshot_module._add_truncation_caveat(updated)

        assert updated.snapshot_caveats == [SNAPSHOT_TRUNCATED_CAVEAT]
        assert again is updated

    def test_apply_size_budget_trims_strings_and_related_records(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot()

        def fake_snapshot_size(current_snapshot: SimulationSnapshot) -> int:
            # After all trimming and caveat, return size within budget
            if (
                current_snapshot.simulation.notes_markdown is None
                and not current_snapshot.artifacts
                and not current_snapshot.links
                and SNAPSHOT_TRUNCATED_CAVEAT in current_snapshot.snapshot_caveats
            ):
                return 5
            if current_snapshot.simulation.notes_markdown is None:
                return 200
            if (
                len(current_snapshot.artifacts),
                len(current_snapshot.links),
            ) in {(2, 3), (2, 2)}:
                return 200
            if (len(current_snapshot.artifacts), len(current_snapshot.links)) == (1, 2):
                return 50
            return 200

        monkeypatch.setattr(snapshot_module, "_snapshot_size", fake_snapshot_size)

        trimmed = snapshot_module._apply_size_budget(
            snapshot,
            _SnapshotSizeBudget(max_chars=10),
        )

        assert trimmed.artifacts == []
        assert trimmed.links == []
        assert trimmed.simulation.notes_markdown is None
        assert trimmed.simulation.description is None
        assert trimmed.simulation.key_features is None
        assert trimmed.simulation.known_issues is None
        assert trimmed.simulation.extra == {}
        assert SNAPSHOT_TRUNCATED_CAVEAT in trimmed.snapshot_caveats

    def test_apply_size_budget_drops_remaining_artifacts_after_trim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot().model_copy(
            update={
                "artifacts": [SnapshotArtifact(kind="output", uri="/output.nc")],
                "links": [],
            }
        )
        sizes = iter([200, 0, 200, 200, 0, 0, 0])

        monkeypatch.setattr(
            snapshot_module,
            "_snapshot_size",
            lambda current_snapshot: next(sizes),
        )

        trimmed = snapshot_module._apply_size_budget(
            snapshot,
            _SnapshotSizeBudget(max_chars=10),
        )

        assert trimmed.artifacts == []

    def test_apply_size_budget_drops_remaining_links_after_trim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot().model_copy(
            update={
                "artifacts": [],
                "links": [SnapshotLink(kind="docs", url="https://example.com/docs")],
            }
        )
        sizes = iter([200, 0, 200, 0, 200, 0, 0])

        monkeypatch.setattr(
            snapshot_module,
            "_snapshot_size",
            lambda current_snapshot: next(sizes),
        )

        trimmed = snapshot_module._apply_size_budget(
            snapshot,
            _SnapshotSizeBudget(max_chars=10),
        )

        assert trimmed.links == []

    def test_apply_size_budget_raises_when_required_fields_too_large(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot = _make_snapshot().model_copy(
            update={
                "artifacts": [],
                "links": [],
            }
        )

        monkeypatch.setattr(
            snapshot_module,
            "_snapshot_size",
            lambda current_snapshot: 200,
        )

        with pytest.raises(
            SnapshotBudgetExceededError,
            match=r"Snapshot size 200 exceeds budget 10.*Required fields are too large",
        ) as exc_info:
            snapshot_module._apply_size_budget(
                snapshot,
                _SnapshotSizeBudget(max_chars=10),
            )

        assert exc_info.value.snapshot.artifacts == []
        assert exc_info.value.snapshot.links == []
        assert exc_info.value.snapshot.simulation.notes_markdown is None
        assert exc_info.value.snapshot.simulation.description is None
        assert exc_info.value.snapshot.simulation.key_features is None
        assert exc_info.value.snapshot.simulation.known_issues is None
        assert exc_info.value.snapshot.simulation.extra == {}
        assert SNAPSHOT_TRUNCATED_CAVEAT in exc_info.value.snapshot.snapshot_caveats

    def test_build_snapshot_merges_case_links_with_simulation_precedence(self) -> None:
        case = Case(
            id=uuid4(),
            name="snapshot-case",
            machine_id=uuid4(),
            hpc_username="snapshot-user",
            case_group="snapshot-group",
        )
        simulation = Simulation(
            id=uuid4(),
            case=case,
            case_id=case.id,
            execution_id="snapshot-exec",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            simulation_type=SimulationType.EXPERIMENTAL,
            status=SimulationStatus.COMPLETED,
            initialization_type="startup",
            simulation_start_date=date(2024, 1, 1),
            created_by=uuid4(),
            last_updated_by=uuid4(),
            ingestion_id=uuid4(),
            extra={},
        )
        case.links = [
            ExternalLink(
                case=case,
                case_id=case.id,
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/case-only",
                label="Case only",
            ),
            ExternalLink(
                case=case,
                case_id=case.id,
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/shared",
                label="Case shared",
            ),
        ]
        simulation.links = [
            ExternalLink(
                simulation=simulation,
                simulation_id=simulation.id,
                kind=ExternalLinkKind.DIAGNOSTIC,
                url="https://example.com/shared",
                label="Simulation shared",
            )
        ]
        simulation.artifacts = []

        snapshot = snapshot_module.build_simulation_snapshot(simulation)

        assert [(link.url, link.label) for link in snapshot.links] == [
            ("https://example.com/case-only", "Case only"),
            ("https://example.com/shared", "Simulation shared"),
        ]
