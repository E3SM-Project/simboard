from sqlalchemy.orm import Session

from app.features.machine.models import Machine

MACHINE_NAME_ALIASES = {
    "pm": "perlmutter",
    "pm-cpu": "perlmutter",
    "pm-gpu": "perlmutter",
}


def normalize_machine_name_for_storage(machine_name: str) -> str:
    """Normalize machine names for canonical lowercase storage."""
    return machine_name.strip().lower()


def canonicalize_machine_name(machine_name: str) -> str:
    """Normalize external machine names to their canonical SimBoard name."""
    normalized_name = normalize_machine_name_for_storage(machine_name)

    return MACHINE_NAME_ALIASES.get(normalized_name, normalized_name)


def resolve_machine_by_name(db: Session, machine_name: str) -> Machine | None:
    """Resolve a machine by canonical name, accepting known aliases."""
    canonical_name = canonicalize_machine_name(machine_name)

    return db.query(Machine).filter(Machine.name == canonical_name).first()
