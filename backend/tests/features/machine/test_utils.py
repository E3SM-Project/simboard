from sqlalchemy.orm import Session

from app.features.machine.models import Machine
from app.features.machine.utils import (
    canonicalize_machine_name,
    normalize_machine_name_for_storage,
    parse_machine_name,
    resolve_machine_by_name,
)
from tests.features.site.utils import get_or_create_site


class TestCanonicalizeMachineName:
    def test_maps_known_aliases_to_canonical_name(self) -> None:
        assert canonicalize_machine_name("pm") == "perlmutter"
        assert canonicalize_machine_name(" pm-cpu ") == "perlmutter"
        assert canonicalize_machine_name("PM-GPU") == "perlmutter"
        assert canonicalize_machine_name("muller-cpu") == "muller"
        assert canonicalize_machine_name("ALVAREZ-GPU") == "alvarez"

    def test_normalizes_unknown_names(self) -> None:
        assert canonicalize_machine_name(" Frontier ") == "frontier"


class TestNormalizeMachineNameForStorage:
    def test_lowercases_and_trims_without_alias_expansion(self) -> None:
        assert normalize_machine_name_for_storage(" Machine A ") == "machine a"
        assert normalize_machine_name_for_storage("PM") == "pm"


class TestParseMachineName:
    def test_extracts_compute_type_from_known_aliases(self) -> None:
        assert parse_machine_name(" pm-cpu ") == ("perlmutter", "cpu")
        assert parse_machine_name("MULLER-GPU") == ("muller", "gpu")
        assert parse_machine_name("alvarez-cpu") == ("alvarez", "cpu")

    def test_plain_and_unknown_names_have_no_compute_type(self) -> None:
        assert parse_machine_name("perlmutter") == ("perlmutter", None)
        assert parse_machine_name("muller") == ("muller", None)
        assert parse_machine_name("unknown-gpu") == ("unknown-gpu", None)


class TestResolveMachineByName:
    @staticmethod
    def _create_machine(db: Session, name: str) -> Machine:
        machine = Machine(
            name=name,
            site_record=get_or_create_site(db),
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

    def test_resolves_unknown_names_after_lowercase_normalization(
        self, db: Session
    ) -> None:
        machine = self._create_machine(db, "legacy-machine")

        resolved = resolve_machine_by_name(db, " legacy-machine ")

        assert resolved is not None
        assert resolved.id == machine.id
