import pytest
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.simulation.models import Case
from app.scripts.db.seed import (
    DEV_HPC_USERNAME,
    _resolve_seed_case_machine,
    _seed_simulation,
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
            simulations_data=[
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
                simulations_data=[
                    {"machine": {"name": "seed-machine-one"}},
                    {"machine": {"name": "seed-machine-two"}},
                ],
                case_name="mixed_seed_case",
            )


class TestSeedSimulation:
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

        simulation = _seed_simulation(
            db,
            sim_entry={
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

        assert simulation.case_id == case.id
        assert simulation.ingestion_id is not None
        assert simulation.compute_type == "gpu"
