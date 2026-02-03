"""
# Parser Main Entrypoint Requirements

Implement a main entrypoint for the parser that performs file discovery and extraction with the following capabilities:

## Archive Extraction

## Experiment Directory Discovery
  Example: `1085209.251220-105556`

## File Pattern Matching
  - **Required files:**
    - `e3sm_timing.<case>.<LID>`
    - `README.case.<LID>.gz`
    - `GIT_DESCRIBE.<LID>.gz`
    - `CaseStatus.<LID>.gz`
  - **Optional files:**
    - `CaseDocs.<LID>/env_case.xml.<LID>.gz`
    - `CaseDocs.<LID>/env_build.xml.<LID>.gz`
    - Other XML/namelist files in `CaseDocs.<LID>/` (ignored or extra)


## Parsing Workflow
  - Collect absolute paths for required files.
  - Pass each file to its respective parser function:
    - `README.case*` → `readme_case.parse_readme_case`
    - `CaseDocs` XML files → `case_docs.parse_env_files`
    - `e3sm_timing.*` → `e3sm_timing.parse_e3sm_timing`
    - `CaseStatus.*` → `case_status.parse_case_status`

## Directory Layout Example
import os
import re
import tarfile
import zipfile
├── GIT_DESCRIBE.<LID>.gz
├── CaseStatus.<LID>.gz
├── replay.sh.<LID>.gz
├── run_e3sm.sh.<LID>.gz
└── CaseDocs.<LID>/
├── env_case.xml.<LID>.gz
├── env_build.xml.<LID>.gz
└── other XML / namelist files
```
"""

import os
import re
import tarfile
import zipfile
from pathlib import Path

from app.core.logger import _setup_custom_logger
from app.features.upload.parsers.case_docs import parse_env_files
from app.features.upload.parsers.case_status import parse_case_status
from app.features.upload.parsers.e3sm_timing import parse_e3sm_timing
from app.features.upload.parsers.readme_case import parse_readme_case

ExpResults = dict[str, str | None]
AllExpResults = dict[str, ExpResults]

logger = _setup_custom_logger(__name__)


def main_parser(archive_path: str | Path, output_dir: str | Path) -> AllExpResults:
    """
    Main entrypoint for parser workflow.

    Parameters
    ----------
    archive_path : str
        Path to the archive file (.zip, .tar.gz, .tgz).
    output_dir : str
        Directory to extract and process files.

    Returns
    -------
    AllExpResults
        Dictionary mapping experiment directory paths to their parsed results.
    """
    archive_path = str(archive_path)  # Ensure archive_path is a string
    output_dir = str(output_dir)  # Ensure output_dir is a string

    if archive_path.endswith(".zip"):
        _extract_zip(archive_path, output_dir)
    elif archive_path.endswith(".tar.gz") or archive_path.endswith(".tgz"):
        _extract_tar_gz(archive_path, output_dir)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")

    results: AllExpResults = {}

    exp_dirs = _find_experiment_dirs(output_dir)
    logger.info(f"Found {len(exp_dirs)} experiment directories.")

    for exp_dir in exp_dirs:
        files = _locate_files(exp_dir)
        results[exp_dir] = _parse_experiment_files(files)

    logger.info("Completed parsing all experiment directories.")

    return results


def _extract_zip(zip_path: str, extract_to: str) -> None:
    """
    Extracts a ZIP archive to the target directory.

    Parameters
    ----------
    zip_path : str
        Path to the ZIP archive.
    extract_to : str
        Directory to extract files to.

    Returns
    -------
    None
    """
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)


def _extract_tar_gz(tar_gz_path: str, extract_to: str) -> None:
    """
    Extracts a TAR.GZ archive to the target directory.

    Parameters
    ----------
    tar_gz_path : str
        Path to the TAR.GZ archive.
    extract_to : str
        Directory to extract files to.

    Returns
    -------
    None
    """
    with tarfile.open(tar_gz_path, "r:gz") as tar_ref:
        tar_ref.extractall(extract_to)


def _find_experiment_dirs(root_dir: str) -> list[str]:
    """
    Recursively search for experiment directories matching the pattern: <digits>.<digits>-<digits>

    Parameters
    ----------
    root_dir : str
        Root directory to search.

    Returns
    -------
    list[str]
        List of absolute paths to matching directories.
    """
    exp_dir_pattern = re.compile(r"\d+\.\d+-\d+$")
    matches: list[str] = []

    for dirpath, dirnames, _ in os.walk(root_dir):
        for dirname in dirnames:
            if exp_dir_pattern.match(dirname):
                matches.append(os.path.join(dirpath, dirname))

    return matches


def _locate_files(exp_dir: str) -> ExpResults:  # noqa: C901
    """
    Locate required and optional files in the experiment directory.

    Parameters
    ----------
    exp_dir : str
        Path to the experiment directory.

    Returns
    -------
    ExpResults
        Dictionary with keys for each file type and absolute paths as values.
    """
    files: ExpResults = {
        "e3sm_timing": None,
        "readme_case": None,
        "git_describe": None,
        "case_status": None,
        "case_docs_env_case": None,
        "case_docs_env_build": None,
    }

    for fname in os.listdir(exp_dir):
        fpath = os.path.join(exp_dir, fname)
        if re.match(r"e3sm_timing\..*\..*", fname):
            files["e3sm_timing"] = fpath
        elif re.match(r"GIT_DESCRIBE\..*\.gz", fname):
            files["git_describe"] = fpath
        elif re.match(r"CaseStatus\..*\.gz", fname):
            files["case_status"] = fpath
        elif re.match(r"replay\.sh\..*\.gz", fname):
            files["replay_sh"] = fpath

    for subdir in os.listdir(exp_dir):
        subdir_path = os.path.join(exp_dir, subdir)
        if os.path.isdir(subdir_path) and subdir.startswith("CaseDocs"):
            for docfile in os.listdir(subdir_path):
                docpath = os.path.join(subdir_path, docfile)

                if re.match(r"README\.case\..*\.gz", docfile):
                    files["readme_case"] = docpath
                if re.match(r"env_case\.xml\..*\.gz", docfile):
                    files["case_docs_env_case"] = docpath
                elif re.match(r"env_build\.xml\..*\.gz", docfile):
                    files["case_docs_env_build"] = docpath

    return files


def _parse_experiment_files(files: dict[str, str | None]) -> ExpResults:
    """
    Pass discovered files to their respective parser functions.

    Parameters
    ----------
    files : dict[str, str | None]
        Dictionary of file paths for each file type.

    Returns
    -------
    ExpResults
        Dictionary with parsed results from each file type.
    """
    results: ExpResults = {}

    if files["readme_case"]:
        rc = parse_readme_case(files["readme_case"])
        results.update({k: v for k, v in rc.items() if v is not None})
    if files["e3sm_timing"]:
        et = parse_e3sm_timing(files["e3sm_timing"])
        results.update({k: v for k, v in et.items() if v is not None})
    if files["case_status"]:
        cs = parse_case_status(files["case_status"])
        results.update({k: v for k, v in cs.items() if v is not None})
    if files["case_docs_env_case"] and files["case_docs_env_build"]:
        env_case_results = parse_env_files(
            files["case_docs_env_case"], files["case_docs_env_case"]
        )
        results.update({k: v for k, v in env_case_results.items() if v is not None})

    return results
