"""
E3SM Timing File Parser

Parses E3SM timing files (plain or gzipped) and extracts core simulation metadata including:
- Case name
- Machine name
- User
- LID
- Date
- Grid resolution
- Compset
- Run configuration (stop option, stop_n, run length)

Reference: https://github.com/tomvothecoder/pace/blob/master/portal/pace/e3sm/e3smParser/parseE3SMTiming.py
Analysis: https://github.com/tomvothecoder/pace/blob/copilot/analyze-e3sm-metadata-parsing/E3SM_PARSING_ANALYSIS.md
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.features.upload.parsers.utils import _open_text


def parse_e3sm_timing(path: str | Path) -> dict[str, Any]:
    """Parse an E3SM timing file and extract metadata fields.

    Parameters
    ----------
    path : str or Path
        Path to the E3SM timing file (plain text or .gz).

    Returns
    -------
    dict
        Dictionary with all relevant fields, including nested run config.
    """
    path = Path(path)
    text = _open_text(path)
    lines = text.splitlines()

    metadata_fields = {
        "case": r"Case\s*[:=]\s*(.+)",
        "machine": r"Machine\s*[:=]\s*(.+)",
        "user": r"User\s*[:=]\s*(.+)",
        "lid": r"LID\s*[:=]\s*(.+)",
        "date_str": r"Curr Date\s*[:=]\s*(.+)",
        "grid_long": r"grid\s*[:=]\s*(.+)",
        "compset_long": r"compset\s*[:=]\s*(.+)",
        "run_length": r"run length\s*[:=]\s*(.+)",
    }

    metadata = {
        key: _extract(lines, pattern) for key, pattern in metadata_fields.items()
    }

    date = None

    if metadata["date_str"]:
        try:
            date = datetime.strptime(metadata["date_str"], "%a %b %d %H:%M:%S %Y")
        except ValueError:
            date = metadata["date_str"]  # fallback to raw string if format fails

    # Extract run configuration
    stop_option, stop_n = _extract_stop_option_and_stop_n(lines)

    result = {
        "case": metadata["case"],
        "machine": metadata["machine"],
        "user": metadata["user"],
        "lid": metadata["lid"],
        "date": date,
        "grid_long": metadata["grid_long"],
        "compset_long": metadata["compset_long"],
        "run_config": {
            "stop_option": stop_option,
            "stop_n": stop_n,
            "run_length": metadata["run_length"],
        },
    }

    return result


def _extract(lines: list[str], pattern: str, group: int = 1) -> Optional[str]:
    """Extract the first regex group matching a pattern from a list of lines.

    Parameters
    ----------
    lines : list of str
        Lines to search.
    pattern : str
        Regex pattern to match.
    group : int, optional
        Group number to extract (default is 1).

    Returns
    -------
    str or None
        The matched group, or None if not found.
    """
    for line in lines:
        m = re.match(pattern, line.strip())

        if m:
            return m.group(group).strip()

    return None


def _extract_stop_option_and_stop_n(
    lines: list[str],
) -> tuple[Optional[str], Optional[str]]:
    stop_option = None
    """
    Extract stop_option and stop_n from lines, handling both same-line and
    separate-line cases.

    Parameters
    ----------
    lines : list of str
        Lines to search.

    Returns
    -------
    tuple of (str or None, str or None)
        stop_option and stop_n values.
    """
    stop_option: str | None = None
    stop_n: str | None = None

    for line in lines:
        m = re.match(r"stop option\s*[:=]\s*([^,]+)", line.strip())

        if m:
            stop_option = m.group(1).strip()
            m2 = re.search(r"stop_n\s*[=:]\s*(\d+)", line)

            if m2:
                stop_n = m2.group(1).strip()

            break

    if stop_n is None:
        stop_n = _extract(lines, r"stop_n\s*[=:]\s*(.+)")

    return stop_option, stop_n
