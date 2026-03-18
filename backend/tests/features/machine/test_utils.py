from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.machine.utils import (
    canonicalize_machine_name,
    resolve_machine_by_name,
)


class TestCanonicalizeMachineName:
    def test_maps_known_aliases_to_canonical_name(self) -> None:
        assert canonicalize_machine_name("pm") == "perlmutter"
        assert canonicalize_machine_name(" pm-cpu ") == "perlmutter"
        assert canonicalize_machine_name("PM-GPU") == "perlmutter"

    def test_normalizes_unknown_names(self) -> None:
        assert canonicalize_machine_name(" Frontier ") == "frontier"


class TestResolveMachineByName:
    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        machine = Machine(
            name=name,
            site="Test Site",
            architecture="x86_64",
            scheduler="SLURM",
            gpu=False,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return machine

    def test_resolves_alias_with_exact_canonical_match(self, db: Session) -> None:
        machine = db.query(Machine).filter(Machine.name == "perlmutter").one()

        resolved = resolve_machine_by_name(db, "pm")

        assert resolved is not None
        assert resolved.id == machine.id

    def test_falls_back_to_case_insensitive_match_for_legacy_rows(
        self, db: Session
    ) -> None:
        machine = self._create_machine(db, "Legacy-Machine")

        resolved = resolve_machine_by_name(db, " legacy-machine ")

        assert resolved is not None
        assert resolved.id == machine.id
