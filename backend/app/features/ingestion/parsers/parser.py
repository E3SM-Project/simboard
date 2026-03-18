"""
Main parser module for processing execution upload archives.

This module extracts and parses case directories from simulation performance
archives. It handles incomplete or failed runs gracefully skipping directories
missing required metadata files and logging warning instead of aborting the
entire ingest.

Key behaviors:
  - Supports .zip, .tar.gz, and .tgz archive formats, or already-extracted dirs.
  - Recursively loops over each case directories and finds execution directories
    matching pattern <digits>.<digits>-<digits>.
    - Example: v3.LR.historical_101 (case)  -> 1085209.251220-105556 (execution)
  - Required and optional metadata files are discovered and parsed per execution dir.
  - Only directories with all required files are included in results.
  - Skipped/incomplete runs are counted and logged.
  - Parsing is deterministic: execution subdirectories are sorted to ensure
    reproducible canonical run selection.

This parser is used by the ingestion workflow to provide a consistent,
reliable mapping from raw archive contents to structured simulation metadata.
"""

import os
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, Iterable, TypedDict

from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.case_docs import (
    parse_env_build,
    parse_env_case,
    parse_env_run,
)
from app.features.ingestion.parsers.case_status import parse_case_status
from app.features.ingestion.parsers.e3sm_timing import parse_e3sm_timing
from app.features.ingestion.parsers.git_info import (
    parse_git_config,
    parse_git_describe,
    parse_git_status,
)
from app.features.ingestion.parsers.readme_case import parse_readme_case
from app.features.ingestion.parsers.types import ParsedSimulation
from app.features.simulation.enums import SimulationStatus

SimulationFiles = dict[str, str | None]

logger = _setup_custom_logger(__name__)


class FileSpec(TypedDict, total=False):
    """Specifications for each file type to be parsed."""

    pattern: str
    location: str
    parser: Callable
    required: bool


FILE_SPECS: dict[str, FileSpec] = {
    "case_docs_env_case": {
        "pattern": r"env_case\.xml\..*\.gz",
        "location": "casedocs",
        "parser": parse_env_case,
        "required": True,
    },
    "case_docs_env_build": {
        "pattern": r"env_build\.xml\..*\.gz",
        "location": "casedocs",
        "parser": parse_env_build,
        "required": True,
    },
    "case_docs_env_run": {
        "pattern": r"env_run\.xml\..*",
        "location": "casedocs",
        "parser": parse_env_run,
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
        "required": False,
    },
    "e3sm_timing": {
        "pattern": r"e3sm_timing\..*",
        "location": "root",
        "parser": parse_e3sm_timing,
        "required": True,
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
        "required": False,
    },
    "git_status": {
        "pattern": r"GIT_STATUS\..*\.gz",
        "location": "root",
        "parser": parse_git_status,
        "required": False,
    },
}


def main_parser(
    archive_path: str | Path, output_dir: str | Path
) -> tuple[list[ParsedSimulation], int]:
    """Main entrypoint for parser workflow.

    Parses case directories from a performance archive, handling incomplete or
    failed runs gracefully. Directories missing required metadata files are
    skipped with a warning rather than aborting the entire ingestion.

    Within each case (parent directory), execution subdirectories are sorted
    deterministically so that canonical run selection is reproducible.

    Parameters
    ----------
    archive_path : str
        Path to the archive file (.zip, .tar.gz, .tgz) or an already-extracted
        directory.
    output_dir : str
        Directory to extract and process files.

    Returns
    -------
    tuple[list[ParsedSimulation], int]
        Parsed simulations in deterministic execution-directory order and the
        count of skipped incomplete runs. Only directories that contain all
        required metadata files and a timing-file LID are included.
    """
    archive_path = str(archive_path)
    output_dir = str(output_dir)
    search_root = output_dir

    if _is_supported_archive(archive_path):
        _extract_archive(archive_path, output_dir)
    else:
        if not os.path.isdir(archive_path):
            raise ValueError(f"Unsupported archive format: {archive_path}")

        search_root = archive_path

    case_to_executions_dirs = _map_case_to_execution_dirs(search_root)
    logger.info(
        f"Found {sum(len(dirs) for dirs in case_to_executions_dirs.values())} case "
        f"directories across {len(case_to_executions_dirs)} base directories."
    )

    if not case_to_executions_dirs:
        raise FileNotFoundError(
            f"No cases or execution directories found under '{search_root}'. "
            "Expected to find at least one case directory containing execution "
            "directories matching pattern: <digits>.<digits>-<digits>"
        )

    results: list[ParsedSimulation] = []
    skipped_count = 0

    for case_dir, exec_dirs in case_to_executions_dirs.items():
        sorted_exec_dirs = sorted(exec_dirs)
        logger.info(
            f"Processing case directory: {case_dir} with {len(sorted_exec_dirs)} "
            "execution subdirectories."
        )

        for exec_dir in sorted_exec_dirs:
            try:
                metadata_files = _locate_metadata_files(exec_dir)
                results.append(_parse_all_files(exec_dir, metadata_files))
            except FileNotFoundError as exc:
                logger.warning(f"Skipping incomplete run in '{exec_dir}': {exc}")
                skipped_count += 1

                continue

    if skipped_count:
        logger.info(
            f"Skipped {skipped_count} incomplete run(s) missing required files."
        )

    logger.info("Completed parsing all execution directories.")

    return results, skipped_count


def _extract_archive(archive_path: str, output_dir: str) -> None:
    """Extracts supported archive formats to the target directory."""
    if archive_path.endswith(".zip"):
        _extract_zip(archive_path, output_dir)
    elif archive_path.endswith((".tar.gz", ".tgz")):
        _extract_tar_gz(archive_path, output_dir)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")


def _is_supported_archive(path: str) -> bool:
    """Return True if path has a supported archive extension."""
    return path.endswith((".zip", ".tar.gz", ".tgz"))


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


def _extractall_with_filter(tar_ref: tarfile.TarFile, path: str) -> None:
    """Extract tar members while filtering out unsafe types."""
    tar_ref.extractall(path, filter=_tar_member_filter)


def _safe_extract(
    extract_to: str, member_names: Iterable[str], extract_func: Callable[[str], None]
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


def _map_case_to_execution_dirs(root_dir: str) -> dict[str, list[str]]:
    """Maps case directories to their execution subdirectories.

    Loops over case directories and search for execution directories matching
    the pattern <digits>.<digits>-<digits> (<jobid>.<starttime>-<endtime>).

    Parameters
    ----------
    root_dir : str
        Root directory to start searching for case directories. This is typically
        the output directory where the archive was extracted or the provided
        directory if it was already extracted.

    Return
    ------
    dict[str, list[str]]
        Mapping of case directory names to lists of full paths for their execution
        subdirectories.

    Example
    -------
        {
            "v3.LR.historical": [
                "/path/to/v3.LR.historical/1085209.251220-105556",
                "/path/to/v3.LR.historical/1085209.251221-105557",
            ],
            ...
        }
    """
    exp_dir_pattern = re.compile(r"\d+\.\d+-\d+$")
    grouped_matches: dict[str, list[str]] = {}

    for dirpath, dirnames, _ in os.walk(root_dir):
        for dirname in dirnames:
            if exp_dir_pattern.match(dirname):
                parent_dir = os.path.basename(dirpath)
                full_path = os.path.join(dirpath, dirname)

                grouped_matches.setdefault(parent_dir, []).append(full_path)

    return grouped_matches


def _locate_metadata_files(exp_dir: str) -> SimulationFiles:
    """Locate required and optional files in the execution directory."""
    files: SimulationFiles = {key: None for key in FILE_SPECS}

    files = _find_root_files(exp_dir, files)
    files = _find_casedocs_files(exp_dir, files)

    _check_missing_files(files, exp_dir)

    return files


def _find_file_in_dir(directory: str, pattern: str) -> str | None:
    """Find a file matching the pattern in the specified directory.

    Raises
    ------
    ValueError
        If multiple files match the pattern.
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
    """Find files located in the root of the execution directory."""
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
            "Required files not found in execution directory "
            f"'{exp_dir}': {', '.join(missing_required)}"
        )

    missing_optional = [
        key
        for key, spec in FILE_SPECS.items()
        if not spec.get("required", False) and not files.get(key)
    ]
    if missing_optional:
        logger.warning(
            "Optional files missing in execution directory "
            f"'{exp_dir}': {', '.join(missing_optional)}"
        )


def _parse_all_files(exec_dir: str, files: dict[str, str | None]) -> ParsedSimulation:
    """Pass discovered files to their respective parser functions.

    Parameters
    ----------
    files : dict[str, str | None]
        Dictionary of file paths for each file type.

    Returns
    -------
    ParsedSimulation
        Typed archive-derived metadata for one execution directory.
    """
    metadata: dict[str, str | None] = {}
    case_status_metadata: dict[str, str | None] | None = None

    for key, spec in FILE_SPECS.items():
        path = files.get(key)
        if not path:
            continue

        parser: Callable = spec["parser"]
        parsed_metadata = parser(path)

        if key == "case_status":
            case_status_metadata = parsed_metadata
            continue

        metadata.update(parsed_metadata)

    # CaseStatus reflects the latest case.run attempt, so its status and run
    # timestamps should override timing-file values when the artifact exists.
    if case_status_metadata is not None:
        metadata.update(case_status_metadata)

    execution_id = _resolve_execution_id(metadata.get("execution_id"), exec_dir)

    return ParsedSimulation(
        execution_dir=exec_dir,
        execution_id=execution_id,
        case_name=metadata.get("case_name"),
        case_group=metadata.get("case_group"),
        machine=metadata.get("machine"),
        hpc_username=metadata.get("user"),
        compset=metadata.get("compset"),
        compset_alias=metadata.get("compset_alias"),
        grid_name=metadata.get("grid_name"),
        grid_resolution=metadata.get("grid_resolution"),
        campaign=metadata.get("campaign"),
        experiment_type=metadata.get("experiment_type"),
        initialization_type=metadata.get("initialization_type"),
        simulation_start_date=metadata.get("simulation_start_date"),
        simulation_end_date=metadata.get("simulation_end_date"),
        run_start_date=metadata.get("run_start_date"),
        run_end_date=metadata.get("run_end_date"),
        compiler=metadata.get("compiler"),
        git_repository_url=metadata.get("git_repository_url"),
        git_branch=metadata.get("git_branch"),
        git_tag=metadata.get("git_tag"),
        git_commit_hash=metadata.get("git_commit_hash"),
        status=metadata.get("status") or SimulationStatus.UNKNOWN.value,
    )


def _resolve_execution_id(execution_id: str | None, exec_dir: str) -> str:
    """Return a stable execution_id or treat the run as incomplete."""
    if execution_id is None:
        raise FileNotFoundError(
            f"Required timing-file LID missing for execution directory '{exec_dir}'"
        )

    normalized = execution_id.strip()
    if not normalized:
        raise FileNotFoundError(
            f"Required timing-file LID missing for execution directory '{exec_dir}'"
        )

    exec_dir_basename = os.path.basename(exec_dir)
    if exec_dir_basename and exec_dir_basename != normalized:
        logger.warning(
            "Timing-file LID '%s' does not match execution directory '%s'. "
            "Using execution directory basename as execution_id.",
            normalized,
            exec_dir_basename,
        )

        return exec_dir_basename

    return normalized
