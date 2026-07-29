from datetime import date, datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.features.catalog.models import Case, Execution, MetadataChange
from app.features.machine.models import Machine
from app.features.user.models import User, UserRole
from app.scripts.db.rollback_seed import DEV_EMAIL, rollback_seed
from app.scripts.db.seed import (
    DEV_HPC_USERNAME,
    _resolve_seed_case_machine,
    _seed_execution,
)
from tests.features.site.utils import get_or_create_site


class TestResolveSeedCaseMachine:
    def test_returns_machine_for_single_machine_case(self, db: Session) -> None:
        machine = Machine(
            name="seed-machine",
            site_record=get_or_create_site(db),
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(machine)
        db.commit()

        resolved = _resolve_seed_case_machine(
            db,
            executions_data=[
                {"machine": {"name": "seed-machine"}},
                {"machine": {"name": "seed-machine"}},
            ],
            case_name="seed_case",
        )

        assert resolved.id == machine.id

    def test_rejects_mixed_machine_case(self, db: Session) -> None:
        db.add_all(
            [
                Machine(
                    name="seed-machine-one",
                    site_record=get_or_create_site(db),
                    architecture="x86_64",
                    scheduler="slurm",
                    gpu=False,
                ),
                Machine(
                    name="seed-machine-two",
                    site_record=get_or_create_site(db),
                    architecture="x86_64",
                    scheduler="slurm",
                    gpu=False,
                ),
            ]
        )
        db.commit()

        with pytest.raises(ValueError, match="mixes machines"):
            _resolve_seed_case_machine(
                db,
                executions_data=[
                    {"machine": {"name": "seed-machine-one"}},
                    {"machine": {"name": "seed-machine-two"}},
                ],
                case_name="mixed_seed_case",
            )


class TestSeedExecution:
    def test_strips_seed_only_identity_fields(
        self, db: Session, normal_user_sync
    ) -> None:
        machine = Machine(
            name="seed-machine",
            site_record=get_or_create_site(db),
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        db.add(machine)
        db.flush()

        case = Case(
            name="seed-case",
            machine_id=machine.id,
            hpc_username=DEV_HPC_USERNAME,
        )
        db.add(case)
        db.flush()

        execution = _seed_execution(
            db,
            execution_entry={
                "machine": {"name": "seed-machine"},
                "machineId": str(machine.id),
                "hpcUsername": "override-me",
                "executionId": "1081156.251218-200923",
                "compset": "AQUAPLANET",
                "compsetAlias": "QPC4",
                "gridName": "f19_f19",
                "gridResolution": "1.9x2.5",
                "initializationType": "startup",
                "simulationType": "production",
                "status": "created",
                "simulationStartDate": "2023-01-01T00:00:00Z",
                "computeType": "gpu",
            },
            case=case,
            case_name="seed-case",
            user_id=normal_user_sync["id"],
        )

        assert execution.case_id == case.id
        assert execution.ingestion_id is not None
        assert execution.compute_type == "gpu"
        assert execution.simulation_start_date == date(2023, 1, 1)


class TestRollbackSeed:
    def test_removes_seed_history_and_preserves_unrelated_history(
        self, db: Session, normal_user_sync
    ) -> None:
        machine = Machine(
            name="rollback-seed-machine",
            site_record=get_or_create_site(db),
            architecture="x86_64",
            scheduler="slurm",
            gpu=False,
        )
        dev_user = User(
            email=DEV_EMAIL,
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        db.add_all([machine, dev_user])
        db.flush()

        seeded_case = Case(
            name="rollback-seeded-case",
            machine_id=machine.id,
            hpc_username=DEV_HPC_USERNAME,
        )
        unrelated_case = Case(
            name="rollback-unrelated-case",
            machine_id=machine.id,
            hpc_username="unrelated-user",
        )
        db.add_all([seeded_case, unrelated_case])
        db.flush()

        seeded_execution = _seed_execution(
            db,
            execution_entry={
                "machine": {"name": machine.name},
                "executionId": "rollback-seeded-execution",
                "compset": "AQUAPLANET",
                "compsetAlias": "QPC4",
                "gridName": "f19_f19",
                "gridResolution": "1.9x2.5",
                "initializationType": "startup",
                "simulationType": "production",
                "status": "created",
                "simulationStartDate": "2023-01-01T00:00:00Z",
            },
            case=seeded_case,
            case_name=seeded_case.name,
            user_id=dev_user.id,
        )
        now = datetime.now(timezone.utc)
        seeded_execution_history = MetadataChange(
            entity_type="execution",
            entity_id=seeded_execution.id,
            field_name="description",
            old_value=None,
            new_value="Edited seed",
            editor_id=normal_user_sync["id"],
            changed_at=now,
        )
        seeded_case_history = MetadataChange(
            entity_type="case",
            entity_id=seeded_case.id,
            field_name="description",
            old_value=None,
            new_value="Edited seed case",
            editor_id=normal_user_sync["id"],
            changed_at=now,
        )
        unrelated_history = MetadataChange(
            entity_type="case",
            entity_id=unrelated_case.id,
            field_name="description",
            old_value=None,
            new_value="Keep me",
            editor_id=normal_user_sync["id"],
            changed_at=now,
        )
        dev_authored_history = MetadataChange(
            entity_type="case",
            entity_id=unrelated_case.id,
            field_name="notes_markdown",
            old_value=None,
            new_value="Remove with dummy editor",
            editor_id=dev_user.id,
            changed_at=now,
        )
        db.add_all(
            [
                seeded_execution_history,
                seeded_case_history,
                unrelated_history,
                dev_authored_history,
            ]
        )
        db.commit()

        rollback_seed(db)

        assert db.get(Execution, seeded_execution.id) is None
        assert db.get(Case, seeded_case.id) is None
        assert db.get(User, dev_user.id) is None
        assert db.get(Case, unrelated_case.id) is not None
        assert db.get(MetadataChange, seeded_execution_history.id) is None
        assert db.get(MetadataChange, seeded_case_history.id) is None
        assert db.get(MetadataChange, dev_authored_history.id) is None
        assert db.get(MetadataChange, unrelated_history.id) is not None
