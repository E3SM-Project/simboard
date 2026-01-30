import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from app.features.upload.parsers import (
    parse_e3sm_timing,
    parse_env_build,
    parse_env_case,
    parse_git_describe,
    parse_readme_case,
)


class ParsedExperiment:
    case_name: str
    machine_name: str
    simulation_start_date: datetime

    compset: str
    compset_alias: str
    grid_name: str
    grid_resolution: str

    git_tag: str | None
    git_commit_hash: str | None

    compiler: str | None
    group_name: str | None

    extra: dict


@dataclass
class ParsedExperimentResult:
    experiments: List[ParsedExperiment]
    warnings: List[str]
    errors: List[str]


def ingest_archive(archive_path: Path) -> ParsedExperimentResult:
    extract_dir = archive_path.parent / "extracted"
    extract_dir.mkdir(exist_ok=True)

    _extract_archive(archive_path, extract_dir)

    exp_dirs = [
        p for p in extract_dir.iterdir() if p.is_dir() and p.name.startswith("exp")
    ]

    if not exp_dirs:
        return ParsedExperimentResult(
            experiments=[],
            warnings=[],
            errors=["No experiment directories found"],
        )

    experiments = []
    warnings: list[str] = []
    errors: list[str] = []

    for exp in exp_dirs:
        try:
            experiments.append(_parse_experiment(exp, warnings))
        except ValueError as e:
            errors.append(str(e))

    return ParsedExperimentResult(
        experiments=experiments,
        warnings=warnings,
        errors=errors,
    )


def _parse_experiment(exp_dir: Path, warnings: list[str]) -> ParsedExperiment:
    timing_file = _find_required(exp_dir, "e3sm_timing")
    readme_file = _find_required(exp_dir, "README.case")
    git_file = _find_required(exp_dir, "GIT_DESCRIBE")

    timing = parse_e3sm_timing(timing_file)
    readme = parse_readme_case(readme_file)
    version = parse_git_describe(git_file)

    env_case = _find_optional(exp_dir, "env_case.xml")
    env_build = _find_optional(exp_dir, "env_build.xml")

    group_name = parse_env_case(env_case) if env_case else None
    compiler = parse_env_build(env_build) if env_build else None

    return ParsedExperiment(
        case_name=timing["case"],
        machine_name=timing["machine"],
        simulation_start_date=timing["date"],
        compset=readme["compset"],
        compset_alias=timing["compset_long"],
        grid_name=readme["res"],
        grid_resolution=timing["grid_long"],
        git_tag=version["tag"],
        git_commit_hash=version["hash"],
        compiler=compiler,
        group_name=group_name,
        extra={
            "lid": timing["lid"],
            "user": timing["user"],
            "run_config": timing["run_config"],
        },
    )


def to_simulation_create(parsed, uploaded_by, machine_id):
    from app.features.simulation.schemas import SimulationCreate

    return SimulationCreate(
        name=parsed.case_name,
        case_name=parsed.case_name,
        compset=parsed.compset,
        compset_alias=parsed.compset_alias,
        grid_name=parsed.grid_name,
        grid_resolution=parsed.grid_resolution,
        machine_id=machine_id,
        simulation_start_date=parsed.simulation_start_date,
        compiler=parsed.compiler,
        group_name=parsed.group_name,
        git_tag=parsed.git_tag,
        git_commit_hash=parsed.git_commit_hash,
        extra=parsed.extra,
        created_by=uploaded_by.id,
    )


def _extract_archive(src: Path, dest: Path):
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
    elif tarfile.is_tarfile(src):
        with tarfile.open(src) as t:
            t.extractall(dest)
    else:
        raise ValueError("Unsupported archive format")


def _find_required(base: Path, prefix: str) -> Path:
    for p in base.rglob("*"):
        if p.name.startswith(prefix):
            return p
    raise ValueError(f"Missing required file: {prefix}*")


def _find_optional(base: Path, prefix: str) -> Path | None:
    for p in base.rglob("*"):
        if p.name.startswith(prefix):
            return p
    return None
