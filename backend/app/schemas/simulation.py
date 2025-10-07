from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.artifact import ArtifactIn, ArtifactOut
from app.schemas.base import CamelInModel, CamelOutModel
from app.schemas.link import ExternalLinkIn, ExternalLinkOut


class SimulationCreate(CamelInModel):
    # Configuration
    # ~~~~~~~~~~~~~~
    name: str
    case_name: str
    description: str | None = None
    version_tag: str | None = None
    git_hash: str | None = None
    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str
    parent_simulation_id: UUID | None = None

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    simulation_type: str
    status: str
    campaign_id: str | None = None
    experiment_type_id: str | None = None
    initialization_type: str
    group_name: str | None = None

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID
    simulation_start_date: datetime
    simulation_end_date: datetime | None = None
    run_start_date: datetime | None = None
    run_end_date: datetime | None = None
    compiler: str | None = None

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = None
    known_issues: str | None = None
    notes_markdown: str | None = None

    # Version control
    # ~~~~~~~~~~~~~~~
    branch: str | None = None
    external_repo_url: str | None = None

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: str | None = None
    last_edited_by: str | None = None

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    # extra -- Extra metadata in flexible dictionary/JSON format.
    # Useful for extensions or storing non-core data.
    extra: dict = {}

    # Relationships
    # ~~~~~~~~~~~~~~
    artifacts: list[ArtifactIn] = Field(default_factory=list)
    links: list[ExternalLinkIn] = Field(default_factory=list)


class SimulationOut(CamelOutModel):
    # Configuration
    # ~~~~~~~~~~~~~~
    id: UUID
    name: str
    case_name: str
    description: str | None = None
    version_tag: str | None = None
    git_hash: str | None = None
    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str
    parent_simulation_id: UUID | None = None

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    simulation_type: str
    status: str
    campaign_id: str | None = None
    experiment_type_id: str | None = None
    initialization_type: str
    group_name: str | None = None

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID
    simulation_start_date: datetime
    simulation_end_date: datetime | None = None
    total_years: float | None = None
    run_start_date: datetime | None = None
    run_end_date: datetime | None = None
    compiler: str | None = None

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = None
    known_issues: str | None = None
    notes_markdown: str | None = None

    # Version control
    # ~~~~~~~~~~~~~~~
    branch: str | None = None
    external_repo_url: str | None = None

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: str | None = None
    last_edited_by: str | None = None

    created_at: datetime  # Server-managed field
    updated_at: datetime  # Server-managed field

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    # extra -- Extra metadata in flexible dictionary/JSON format.
    # Useful for extensions or storing non-core data.
    extra: dict = {}

    # Relationships
    # ~~~~~~~~~~~~~~
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    links: list[ExternalLinkOut] = Field(default_factory=list)
