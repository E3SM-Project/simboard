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

from app.features.simulation.schemas import KNOWN_EXPERIMENT_TYPES
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
        "case_name": r"Case\s*[:=]\s*(.+)",
        "machine": r"Machine\s*[:=]\s*(.+)",
        "user": r"User\s*[:=]\s*(.+)",
        "lid": r"LID\s*[:=]\s*(.+)",
        "simulation_start_date": r"Curr Date\s*[:=]\s*(.+)",
        "grid_resolution": r"grid\s*[:=]\s*(.+)",
        "compset_alias": r"compset\s*[:=]\s*(.+)",
        "initialization_type": r"run type\s*[:=]\s*([^,]+)",
        "run_length": r"run length\s*[:=]\s*(.+)",
    }

    metadata = {
        key: _extract(lines, pattern) for key, pattern in metadata_fields.items()
    }

    # Extract metadata that requires special handling
    campaign, experiment_type = _extract_campaign_and_experiment_type(
        metadata.get("case_name")
    )
    simulation_start_date = _parse_simulation_start_date(
        metadata["simulation_start_date"]
    )
    stop_option, stop_n = _extract_stop_option_and_stop_n(lines)

    result = {
        "case_name": metadata["case_name"],
        "campaign": campaign,
        "experiment_type": experiment_type,
        "machine": metadata["machine"],
        "user": metadata["user"],
        "lid": metadata["lid"],
        "simulation_start_date": simulation_start_date,
        "grid_resolution": metadata["grid_resolution"],
        "compset_alias": metadata["compset_alias"],
        "initialization_type": metadata["initialization_type"],
        "run_config": {
            "stop_option": stop_option,
            "stop_n": stop_n,
            "run_length": metadata["run_length"],
        },
    }

    return result


def _extract_campaign_and_experiment_type(
    case_name: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Extract campaign and experiment type from case name.

    Parameters
    ----------
    case_name : str or None
        The case name to parse.

    Returns
    -------
    tuple of (str or None, str or None)
        campaign and experiment_type values.
    """
    campaign = None
    experiment_type = None

    # Example: v3.LR.historical
    if case_name:
        # Remove trailing instance suffix like _0121
        base = re.sub(r"_\d+$", "", case_name)

        # Campaign = everything except the final instance suffix
        campaign = ".".join(base.split(".")[:])

        # Candidate experiment type = last dot token
        candidate = campaign.split(".")[-1]

        if candidate in KNOWN_EXPERIMENT_TYPES:
            experiment_type = candidate

    return campaign, experiment_type


def _parse_simulation_start_date(date_str: Optional[str]) -> Optional[str]:
    """Parse simulation start date string to ISO format.

    Parameters
    ----------
    date_str : str or None
        The date string to parse (e.g., "Tue Jan 10 12:34:56 2023").

    Returns
    -------
    str or None
        ISO formatted date string, or the original string if parsing fails.
    """
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y").isoformat()
    except ValueError:
        # fallback to raw string if format fails
        return date_str


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
