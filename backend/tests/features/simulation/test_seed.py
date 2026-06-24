import pytest
from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.scripts.db.seed import _resolve_seed_case_machine


class TestResolveSeedCaseMachine:
    def test_returns_machine_for_single_machine_case(self, db: Session) -> None:
        machine = Machine(
            name="seed-machine",
            site="Test Site",
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
                    site="Test Site",
                    architecture="x86_64",
                    scheduler="slurm",
                    gpu=False,
                ),
                Machine(
                    name="seed-machine-two",
                    site="Test Site",
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
