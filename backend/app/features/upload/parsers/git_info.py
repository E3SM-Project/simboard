"""
Git Info File Parser

Parses GIT_STATUS.* and GIT_CONFIG.* files to extract:
- Current branch (from GIT_STATUS)
- Git remote URL (from GIT_CONFIG)

Follows the style of e3sm_timing.py.
"""

import re
from pathlib import Path

from app.features.upload.parsers.utils import _open_text


def parse_git_describe(describe_path: str | Path) -> dict[str, str | None]:
    """Parse GIT_DESCRIBE file for the version string.

    Parameters
    ----------
    describe_path : str or Path
        Path to the GIT_DESCRIBE file.

    Returns
    -------
    dict[str, str | None]
        Dictionary with 'git_tag' and 'git_hash' keys.
    """
    describe_path = Path(describe_path)
    describe_lines = _open_text(describe_path).splitlines()
    result: dict[str, str | None] = {"git_tag": None, "git_hash": None}

    for line in describe_lines:
        line = line.strip()
        if line:
            # Example: 3.0.2-55-gea457362f3
            # Tag: up to first dash or end
            tag_match = re.match(r"^([^-]+)", line)
            if tag_match:
                result["git_tag"] = tag_match.group(1)

            # Hash: after '-g'
            hash_match = re.search(r"-g([0-9a-f]+)$", line)
            if hash_match:
                result["git_commit_hash"] = hash_match.group(1)

    return result


def parse_git_status(status_path: str | Path) -> str | None:
    """Parse GIT_STATUS file for current branch.

    Parameters
    ----------
    status_path : str or Path
        Path to the GIT_STATUS file.

    Returns
    -------
    str or None
        Current branch name, or None if not found.
    """
    status_path = Path(status_path)
    status_lines = _open_text(status_path).splitlines()

    return _extract_branch(status_lines)


def parse_git_config(config_path: str | Path) -> str | None:
    """Parse GIT_CONFIG file for remote URL.

    Parameters
    ----------
    config_path : str or Path
        Path to the GIT_CONFIG file.

    Returns
    -------
    str or None
        Remote URL, or None if not found.
    """
    config_path = Path(config_path)
    config_lines = _open_text(config_path).splitlines()

    return _extract_remote_url(config_lines)


def _extract_branch(lines: list[str]) -> str | None:
    """Extract the current branch from GIT_STATUS lines."""
    for line in lines:
        m = re.match(r"On branch (.+)", line.strip())
        if m:
            return m.group(1).strip()

    return None


def _extract_remote_url(lines: list[str]) -> str | None:
    """Extract the remote URL for 'origin' from GIT_CONFIG lines."""
    in_origin = False
    for line in lines:
        if re.match(r'\[remote "origin"\]', line.strip()):
            in_origin = True
            continue
        if in_origin:
            m = re.match(r"url\s*=\s*(.+)", line.strip())
            if m:
                return m.group(1).strip()
            # End of section if another [ starts
            if line.strip().startswith("["):
                break
    return None
