from sqlalchemy import func
from sqlalchemy.orm import Session

from app.features.machine.models import Machine

MACHINE_NAME_ALIASES = {
    "pm": "perlmutter",
    "pm-cpu": "perlmutter",
    "pm-gpu": "perlmutter",
}


def canonicalize_machine_name(machine_name: str) -> str:
    """Normalize external machine names to their canonical SimBoard name."""
    normalized_name = machine_name.strip().lower()

    return MACHINE_NAME_ALIASES.get(normalized_name, normalized_name)


def resolve_machine_by_name(db: Session, machine_name: str) -> Machine | None:
    """Resolve a machine by canonical name, accepting known aliases."""
    canonical_name = canonicalize_machine_name(machine_name)

    machine = db.query(Machine).filter(Machine.name == canonical_name).first()
    if machine is not None:
        return machine

    # Fallback for legacy mixed-case rows until machine names are normalized.
    machine = (
        db.query(Machine).filter(func.lower(Machine.name) == canonical_name).first()
    )

    return machine
