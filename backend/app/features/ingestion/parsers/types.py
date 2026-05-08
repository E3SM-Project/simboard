from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedSimulation:
    """Archive-derived metadata for one parsed execution run."""

    execution_dir: str
    execution_id: str
    case_name: str | None
    case_group: str | None
    machine: str | None
    hpc_username: str | None
    compset: str | None
    compset_alias: str | None
    grid_name: str | None
    grid_resolution: str | None
    campaign: str | None
    experiment_type: str | None
    initialization_type: str | None
    simulation_start_date: str | None
    simulation_end_date: str | None
    run_start_date: str | None
    run_end_date: str | None
    compiler: str | None
    git_repository_url: str | None
    git_branch: str | None
    git_tag: str | None
    git_commit_hash: str | None
    status: str | None
    output_path: str | None = None
    archive_path: str | None = None
    case_root: str | None = None
    postprocessing_script: str | None = None
