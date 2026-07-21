from typing import Literal

from sqlalchemy.orm import Session

from app.features.machine.models import Machine

MACHINE_NAME_ALIASES = {
    "pm": "perlmutter",
    "pm-cpu": "perlmutter",
    "pm-gpu": "perlmutter",
    "muller-cpu": "muller",
    "muller-gpu": "muller",
    "alvarez-cpu": "alvarez",
    "alvarez-gpu": "alvarez",
}


def normalize_machine_name_for_storage(machine_name: str) -> str:
    """Normalize machine names for canonical lowercase storage."""
    return machine_name.strip().lower()


def canonicalize_machine_name(machine_name: str) -> str:
    """Normalize external machine names to their canonical SimBoard name."""
    canonical_name, _ = parse_machine_name(machine_name)
    return canonical_name


def parse_machine_name(
    machine_name: str,
) -> tuple[str, Literal["cpu", "gpu"] | None]:
    """Return canonical machine name and compute type encoded by a known alias."""
    normalized_name = normalize_machine_name_for_storage(machine_name)
    compute_type: Literal["cpu", "gpu"] | None = None

    if normalized_name in MACHINE_NAME_ALIASES:
        if normalized_name.endswith("-cpu"):
            compute_type = "cpu"
        elif normalized_name.endswith("-gpu"):
            compute_type = "gpu"

    return MACHINE_NAME_ALIASES.get(normalized_name, normalized_name), compute_type


def resolve_machine_by_name(db: Session, machine_name: str) -> Machine | None:
    """Resolve a machine by canonical name, accepting known aliases."""
    canonical_name = canonicalize_machine_name(machine_name)

    return db.query(Machine).filter(Machine.name == canonical_name).first()
