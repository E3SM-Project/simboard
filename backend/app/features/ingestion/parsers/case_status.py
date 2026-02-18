import logging
import re
from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from app.features.ingestion.parsers.utils import _get_open_func
from app.features.simulation.enums import SimulationStatus

logger = logging.getLogger(__name__)

TIMESTAMP_PATTERN = r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
CASE_RUN_START_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+starting(?:\s+(?P<job_id>\S+))?\s*$"
)
CASE_RUN_TERMINAL_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+(?P<state>success|error)\b"
)
RUN_STARTDATE_PATTERN = re.compile(r"RUN_STARTDATE=(?P<start_date>\d{4}-\d{2}-\d{2})")
STOP_OPTION_STOP_N_PATTERN = re.compile(
    r"STOP_OPTION=(?P<stop_option>[^,\s]+),STOP_N=(?P<stop_n>\d+)"
)


def parse_case_status(file_path: str) -> dict[str, Any]:
    """
    Parse the case status file and extract relevant information.

    Parameters
    ----------
    file_path : str
        Path to the case status file.

    Returns
    -------
    dict[str, Any]
        A dictionary containing simulation date metadata and latest case.run
        attempt metadata.
    """
    result: dict[str, Any] = {
        "simulation_start_date": None,
        "simulation_end_date": None,
        "run_start_date": None,
        "run_end_date": None,
        "status": None,
    }

    open_func = _get_open_func(file_path)
    try:
        with open_func(file_path, "rt") as file:
            lines = file.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read case status file %s (%s)", file_path, exc)
        return result

    latest_start_idx, latest_start_match = _extract_simulation_dates(
        lines, file_path, result
    )

    _extract_latest_run_metadata(lines, latest_start_idx, latest_start_match, result)

    return result


def _extract_simulation_dates(
    lines: list[str], file_path: str, result: dict[str, Any]
) -> tuple[int | None, re.Match[str] | None]:
    latest_start_idx: int | None = None
    latest_start_match: re.Match[str] | None = None

    for index, line in enumerate(lines):
        run_startdate_match = RUN_STARTDATE_PATTERN.search(line)
        if "RUN_STARTDATE" in line and not run_startdate_match:
            logger.warning(
                f"Malformed RUN_STARTDATE line in {file_path}: {line.strip()}"
            )
        elif run_startdate_match:
            result["simulation_start_date"] = run_startdate_match.group("start_date")

        stop_match = STOP_OPTION_STOP_N_PATTERN.search(line)
        if "STOP_OPTION" in line and "STOP_N" in line and not stop_match:
            logger.warning(
                f"Malformed STOP_OPTION/STOP_N line in {file_path}: {line.strip()}"
            )
        elif stop_match:
            _update_simulation_end_date(file_path, line, stop_match, result)

        start_match = CASE_RUN_START_PATTERN.match(line.strip())
        if start_match:
            latest_start_idx = index
            latest_start_match = start_match

    return latest_start_idx, latest_start_match


def _update_simulation_end_date(
    file_path: str, line: str, stop_match: re.Match[str], result: dict[str, Any]
) -> None:
    stop_option = stop_match.group("stop_option")
    stop_n_str = stop_match.group("stop_n")

    try:
        stop_n = int(stop_n_str)
    except ValueError as exc:
        logger.warning(
            f"Malformed STOP_OPTION/STOP_N line in {file_path}: {line.strip()} ({exc})"
        )
        return

    result["simulation_end_date"] = _calculate_simulation_end_date(
        result["simulation_start_date"], stop_option, stop_n
    )


def _extract_latest_run_metadata(
    lines: list[str],
    latest_start_idx: int | None,
    latest_start_match: re.Match[str] | None,
    result: dict[str, Any],
) -> None:
    if latest_start_idx is None or latest_start_match is None:
        return

    result["run_start_time"] = latest_start_match.group("timestamp")
    result["run_start_date"] = result["run_start_time"]

    for line in lines[latest_start_idx + 1 :]:
        terminal_match = CASE_RUN_TERMINAL_PATTERN.match(line.strip())
        if not terminal_match:
            continue

        result["run_end_time"] = terminal_match.group("timestamp")
        result["run_end_date"] = result["run_end_time"]
        state = terminal_match.group("state")

        if state == "success":
            result["status"] = SimulationStatus.COMPLETED.value
        elif state == "error":
            result["status"] = SimulationStatus.FAILED.value
        return

    result["status"] = SimulationStatus.RUNNING.value


def _calculate_simulation_end_date(
    simulation_start_date: str | None, stop_option: str | None, stop_n: int | None
) -> str | None:
    if not (simulation_start_date and stop_option and stop_n):
        return None

    try:
        start = datetime.strptime(simulation_start_date, "%Y-%m-%d")
    except ValueError:
        return None

    option = stop_option.lower()
    n = stop_n

    if "days" in option:
        end = start + relativedelta(days=n)
    elif "months" in option:
        end = start + relativedelta(months=n)
    elif "years" in option:
        end = start + relativedelta(years=n)
    else:
        return None

    return end.strftime("%Y-%m-%d")
