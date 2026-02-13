"""Main parser module for processing experiment upload archives."""

import os
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, Iterable, TypedDict

from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.case_docs import parse_env_build, parse_env_case
from app.features.ingestion.parsers.case_status import parse_case_status
from app.features.ingestion.parsers.e3sm_timing import parse_e3sm_timing
from app.features.ingestion.parsers.git_info import (
    parse_git_config,
    parse_git_describe,
    parse_git_status,
)
from app.features.ingestion.parsers.readme_case import parse_readme_case

SimulationFiles = dict[str, str | None]
SimulationMetadata = dict[str, str | None]
AllSimulations = dict[str, SimulationMetadata]

logger = _setup_custom_logger(__name__)


# The specifications for each file type to be parsed.
class FileSpec(TypedDict, total=False):
    pattern: str
    location: str
    parser: Callable
    required: bool
    single_value: str


FILE_SPECS: dict[str, FileSpec] = {
    "e3sm_timing": {
        "pattern": r"e3sm_timing\..*\..*",
        "location": "root",
        "parser": parse_e3sm_timing,
        "required": True,
    },
    "readme_case": {
        "pattern": r"README\.case\..*\.gz",
        "location": "casedocs",
        "parser": parse_readme_case,
        "required": True,
    },
    "case_status": {
        "pattern": r"CaseStatus\..*\.gz",
        "location": "root",
        "parser": parse_case_status,
        "required": True,
    },
    "case_docs_env_case": {
        "pattern": r"env_case\.xml\..*\.gz",
        "location": "casedocs",
        "parser": parse_env_case,
        "required": False,
    },
    "case_docs_env_build": {
        "pattern": r"env_build\.xml\..*\.gz",
        "location": "casedocs",
        "parser": parse_env_build,
        "required": False,
    },
    "git_describe": {
        "pattern": r"GIT_DESCRIBE\..*\.gz",
        "location": "root",
        "parser": parse_git_describe,
        "required": True,
    },
    "git_config": {
        "pattern": r"GIT_CONFIG\..*\.gz",
        "location": "root",
        "parser": parse_git_config,
        "single_value": "git_repository_url",
        "required": False,
    },
    "git_status": {
        "pattern": r"GIT_STATUS\..*\.gz",
        "location": "root",
        "parser": parse_git_status,
        "single_value": "git_branch",
        "required": False,
    },
}


def main_parser(archive_path: str | Path, output_dir: str | Path) -> AllSimulations:
    """Main entrypoint for parser workflow.

    Parameters
    ----------
    archive_path : str
        Path to the archive file (.zip, .tar.gz, .tgz).
    output_dir : str
        Directory to extract and process files.

    Returns
    -------
    AllSimulations
        Dictionary mapping experiment directory paths to their parsed simulations.
    """
    archive_path = str(archive_path)
    output_dir = str(output_dir)

    _extract_archive(archive_path, output_dir)

    results: AllSimulations = {}

    exp_dirs = _find_experiment_dirs(output_dir)
    logger.info(f"Found {len(exp_dirs)} experiment directories.")

    if not exp_dirs:
        raise FileNotFoundError(
            f"No experiment directories found in extracted archive at '{output_dir}'. "
            "Expected directory names matching pattern: <digits>.<digits>-<digits>"
        )

    for exp_dir in exp_dirs:
        files = _locate_files(exp_dir)
        results[exp_dir] = _parse_experiment_files(files)

    logger.info("Completed parsing all experiment directories.")

    return results


def _extract_archive(archive_path: str, output_dir: str) -> None:
    """Extracts supported archive formats to the target directory."""
    if archive_path.endswith(".zip"):
        _extract_zip(archive_path, output_dir)
    elif archive_path.endswith((".tar.gz", ".tgz")):
        _extract_tar_gz(archive_path, output_dir)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")


def _extract_zip(zip_path: str, extract_to: str) -> None:
    """Extracts a ZIP archive to the target directory."""
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        _safe_extract(
            extract_to,
            (info.filename for info in zip_ref.infolist()),
            zip_ref.extractall,
        )


def _extract_tar_gz(tar_gz_path: str, extract_to: str) -> None:
    """Extracts a TAR.GZ archive to the target directory."""
    with tarfile.open(tar_gz_path, "r:gz") as tar_ref:
        _safe_extract(
            extract_to,
            (member.name for member in tar_ref.getmembers()),
            lambda path: _extractall_with_filter(tar_ref, path),
        )


def _extractall_with_filter(tar_ref, path: str) -> None:
    """Extract tar members while filtering out unsafe types."""
    tar_ref.extractall(path, filter=_tar_member_filter)


def _safe_extract(
    extract_to: str,
    member_names: Iterable[str],
    extract_func: Callable[[str], None],
) -> None:
    """Validate archive members to prevent path traversal before extraction."""
    base_dir = Path(extract_to).resolve()

    for name in member_names:
        target_path = (base_dir / name).resolve()
        if not _is_within_directory(base_dir, target_path):
            raise ValueError(
                "Archive member path escapes extraction directory: "
                f"{name} -> {target_path}"
            )

    extract_func(extract_to)


def _tar_member_filter(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo:
    """Allow only regular files and directories during tar extraction."""
    if member.isreg() or member.isdir():
        return member

    raise ValueError(f"Blocked unsafe tar member type: {member.name}")


def _is_within_directory(base_dir: Path, target_path: Path) -> bool:
    """Return True if target_path is within base_dir."""
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        return False

    return True


def _find_experiment_dirs(root_dir: str) -> list[str]:
    """
    Recursively search for experiment directories matching the pattern:
    <digits>.<digits>-<digits>
    """
    exp_dir_pattern = re.compile(r"\d+\.\d+-\d+$")
    matches: list[str] = []

    for dirpath, dirnames, _ in os.walk(root_dir):
        for dirname in dirnames:
            if exp_dir_pattern.match(dirname):
                matches.append(os.path.join(dirpath, dirname))

    return matches


def _locate_files(exp_dir: str) -> SimulationFiles:
    """Locate required and optional files in the experiment directory."""
    files: SimulationFiles = {key: None for key in FILE_SPECS}

    files = _find_root_files(exp_dir, files)
    files = _find_casedocs_files(exp_dir, files)
    _check_missing_files(files, exp_dir)

    return files


def _find_file_in_dir(directory: str, pattern: str) -> str | None:
    """Find a file matching the pattern in the specified directory.

    Raises ValueError if multiple files match the pattern.
    """
    matches = []
    for fname in os.listdir(directory):
        if re.match(pattern, fname):
            matches.append(os.path.join(directory, fname))

    if len(matches) > 1:
        raise ValueError(
            f"Multiple files matching pattern '{pattern}' found in {directory}: {matches}"
        )

    return matches[0] if matches else None


def _find_root_files(exp_dir: str, files: SimulationFiles) -> SimulationFiles:
    """Find files located in the root of the experiment directory."""
    for key, spec in FILE_SPECS.items():
        if spec["location"] == "root":
            pattern = str(spec["pattern"])
            files[key] = _find_file_in_dir(exp_dir, pattern)

    return files


def _find_casedocs_files(exp_dir: str, files: SimulationFiles) -> SimulationFiles:
    for key, spec in FILE_SPECS.items():
        if spec["location"] == "casedocs":
            pattern = str(spec["pattern"])
            for subdir in os.listdir(exp_dir):
                subdir_path = os.path.join(exp_dir, subdir)
                if os.path.isdir(subdir_path) and subdir.startswith("CaseDocs"):
                    match = _find_file_in_dir(subdir_path, pattern)
                    if match:
                        files[key] = match
                        break
    return files


def _check_missing_files(files: SimulationFiles, exp_dir: str) -> None:
    missing_required = [
        key
        for key, spec in FILE_SPECS.items()
        if spec.get("required", False) and not files.get(key)
    ]
    if missing_required:
        raise FileNotFoundError(
            f"Required files not found in experiment directory '{exp_dir}': {', '.join(missing_required)}"
        )

    missing_optional = [
        key
        for key, spec in FILE_SPECS.items()
        if not spec.get("required", False) and not files.get(key)
    ]
    if missing_optional:
        logger.warning(
            f"Optional files missing in experiment directory '{exp_dir}': {', '.join(missing_optional)}"
        )


def _parse_experiment_files(files: dict[str, str | None]) -> SimulationMetadata:
    """Pass discovered files to their respective parser functions.

    Parameters
    ----------
    files : dict[str, str | None]
        Dictionary of file paths for each file type.

    Returns
    -------
    SimulationMetadata
        Dictionary with parsed results from each file type.
    """
    metadata: SimulationMetadata = {}

    for key, spec in FILE_SPECS.items():
        path = files.get(key)
        if not path:
            continue

        parser: Callable = spec["parser"]

        if "single_value" not in spec:
            metadata.update(parser(path))
        else:
            metadata[spec["single_value"]] = parser(path)

    populated_fields: SimulationMetadata = {
        "name": metadata.get("case_name"),
        "case_name": metadata.get("case_name"),
        "compset": metadata.get("compset"),
        "compset_alias": metadata.get("compset_alias"),
        "grid_name": metadata.get("grid_name"),
        "grid_resolution": metadata.get("grid_resolution"),
        "campaign": metadata.get("campaign"),
        "experiment_type": metadata.get("experiment_type"),
        "initialization_type": metadata.get("initialization_type"),
        "group_name": metadata.get("group_name"),
        "simulation_start_date": metadata.get("simulation_start_date"),
        "run_start_date": metadata.get("run_start_date"),
        "run_end_date": metadata.get("run_end_date"),
        "compiler": metadata.get("compiler"),
        "git_repository_url": metadata.get("git_repository_url"),
        "git_branch": metadata.get("git_branch"),
        "git_tag": metadata.get("git_tag"),
        "git_commit_hash": metadata.get("git_commit_hash"),
        "created_by": metadata.get("user"),
        "last_updated_by": metadata.get("user"),
        "machine": metadata.get("machine"),
    }

    placeholder_fields: SimulationMetadata = {
        "parent_simulation_id": None,
        "simulation_type": None,
        "status": None,
        "simulation_end_date": None,
        "extra": None,
        "artifacts": None,
        "links": None,
    }

    simulation: SimulationMetadata = {**populated_fields, **placeholder_fields}

    return simulation
