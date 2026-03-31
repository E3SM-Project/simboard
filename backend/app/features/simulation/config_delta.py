from dataclasses import dataclass
from dataclasses import fields as dataclass_fields


@dataclass(frozen=True)
class SimulationConfigSnapshot:
    """Normalized configuration fields used for reference delta comparison."""

    compset: str | None
    compset_alias: str | None
    grid_name: str | None
    grid_resolution: str | None
    initialization_type: str | None
    compiler: str | None
    git_tag: str | None
    git_commit_hash: str | None
    git_branch: str | None
    git_repository_url: str | None
    campaign: str | None
    experiment_type: str | None
    simulation_type: str | None

    @classmethod
    def field_names(cls) -> frozenset[str]:
        """Return the config field set tracked for reference comparisons."""
        return frozenset(field.name for field in dataclass_fields(cls))

    def diff(
        self, other: "SimulationConfigSnapshot"
    ) -> dict[str, dict[str, str | None]]:
        """Return changed config fields relative to another snapshot."""
        delta: dict[str, dict[str, str | None]] = {}

        for field in dataclass_fields(self):
            field_name = field.name
            reference_value = getattr(self, field_name)
            current_value = getattr(other, field_name)
            if reference_value != current_value:
                delta[field_name] = {
                    "reference": reference_value,
                    "current": current_value,
                }

        return delta
