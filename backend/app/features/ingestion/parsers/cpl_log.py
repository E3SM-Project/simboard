"""Execution simulation dates from the initial coupler driver clock."""

import re
from datetime import datetime
from pathlib import Path

from app.features.ingestion.parsers.utils import _open_text


def parse_cpl_log(path: str | Path) -> dict[str, str]:
    """Read Curr Time and Stop Time, not the original run's Start Time.

    Only the first driver clock is authoritative. Component clocks and later
    clock dumps may describe different intervals. Stop Time is the configured
    end of the complete execution, not a termination-record timestamp.
    """
    try:
        text = _open_text(Path(path))
    except (OSError, EOFError, UnicodeDecodeError):
        return {}

    clocks = list(
        re.finditer(r"\(seq_timemgr_clockPrint\)\s+Clock\s*=\s*(\w+)\b", text)
    )
    for index, clock in enumerate(clocks):
        if clock.group(1) != "drv":
            continue
        end = clocks[index + 1].start() if index + 1 < len(clocks) else len(text)
        block = text[clock.end() : end]
        dates: dict[str, str] = {}
        for label, key in (
            ("Curr", "simulation_start_date"),
            ("Stop", "simulation_end_date"),
        ):
            match = re.search(
                rf"\(seq_timemgr_clockPrint\)\s+{label} Time\s*=\s*(\d{{8}})\b",
                block,
            )
            if match:
                try:
                    value = datetime.strptime(match.group(1), "%Y%m%d").date()
                except ValueError:
                    continue
                dates[key] = value.isoformat()
        if (
            dates.get("simulation_start_date")
            and dates.get("simulation_end_date")
            and dates["simulation_end_date"] < dates["simulation_start_date"]
        ):
            return {}
        return dates
    return {}
