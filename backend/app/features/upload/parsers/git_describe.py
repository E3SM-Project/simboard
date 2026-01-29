"""
GIT_DESCRIBE file parser for SimBoard

Extracts:
  - version: first non-empty line (as-is)
  - git_tag: tag portion (if parseable)
  - git_commit_hash: commit hash (if parseable)
"""

import re
from pathlib import Path

from app.features.upload.parsers.utils import _open_text


def parse_git_describe_file(path: str | Path) -> dict[str, str | None]:
    """Parse a GIT_DESCRIBE file (plain or gzipped).

    Parameters
    ----------
    path : str or Path
        Path to the GIT_DESCRIBE file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with version, git_tag, git_commit_hash.
    """
    path = Path(path)

    text = _open_text(path)
    version = None

    for line in text.splitlines():
        line = line.strip()
        if line:
            version = line
            break

    git_tag = None
    git_commit_hash = None

    if version:
        m = re.match(r"^(?P<tag>v[\w.\-]+)(?:-\d+)?-g(?P<hash>[0-9a-f]+)", version)
        if m:
            git_tag = m.group("tag")
            git_commit_hash = m.group("hash")

    result = {
        "version": version,
        "git_tag": git_tag,
        "git_commit_hash": git_commit_hash,
    }

    return result
