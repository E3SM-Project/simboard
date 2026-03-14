import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.features.ingestion.parsers.utils import _open_text


def parse_e3sm_timing(path: str | Path) -> dict[str, Any]:
    """Parse an E3SM timing file and extract run metadata.

    Parameters
    ----------
    path : str or Path
        Path to the E3SM timing file (plain text or .gz).

    Returns
    -------
    dict
        Dictionary with execution and run timing metadata.
    """
    path = Path(path)
    result: dict[str, str | None] = {
        "execution_id": None,
        "run_start_date": None,
        "run_end_date": None,
    }

    try:
        text = _open_text(path)
    except (OSError, UnicodeDecodeError):
        return result

    lines = text.splitlines()

    execution_id = _extract(lines, r"LID\s*[:=]\s*(.+)")
    curr_date = _parse_curr_date(_extract(lines, r"Curr Date\s*[:=]\s*(.+)"))
    init_time = _parse_seconds(_extract(lines, r"Init Time\s*[:=]\s*(.+)"))
    run_time = _parse_seconds(_extract(lines, r"Run Time\s*[:=]\s*(.+)"))
    final_time = _parse_seconds(_extract(lines, r"Final Time\s*[:=]\s*(.+)"))

    result["execution_id"] = execution_id
    if curr_date is not None:
        result["run_end_date"] = curr_date.isoformat(timespec="seconds")

    if (
        curr_date is not None
        and init_time is not None
        and run_time is not None
        and final_time is not None
    ):
        total_seconds = init_time + run_time + final_time
        run_start_date = curr_date - timedelta(seconds=total_seconds)
        result["run_start_date"] = run_start_date.replace(microsecond=0).isoformat()

    return result


def _parse_curr_date(date_str: str | None) -> datetime | None:
    """Parse a timing-file date string."""
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None


def _extract(lines: list[str], pattern: str, group: int = 1) -> str | None:
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


def _parse_seconds(value: str | None) -> float | None:
    """Extract a floating-point seconds value from a timing line."""
    if not value:
        return None

    match = re.search(r"(-?\d+(?:\.\d+)?)", value)
    if not match:
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None
