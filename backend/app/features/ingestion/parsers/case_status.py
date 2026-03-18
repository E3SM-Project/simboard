import re
from pathlib import Path

from app.core.logger import _setup_custom_logger
from app.features.ingestion.parsers.utils import _open_text
from app.features.simulation.enums import SimulationStatus

logger = _setup_custom_logger(__name__)

TIMESTAMP_PATTERN = r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
CASE_RUN_START_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+starting(?:\s+\S+)?\s*$"
)
CASE_RUN_TERMINAL_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+(?P<state>success|error)\b"
)


def parse_case_status(file_path: str | Path) -> dict[str, str | None]:
    """Parse the latest ``case.run`` attempt from ``CaseStatus``.

    ``CaseStatus`` can record multiple attempts for the same execution. The
    latest ``case.run starting`` entry is treated as authoritative and the first
    terminal entry after it determines the run status.
    """
    file_path = Path(file_path)
    result: dict[str, str | None] = {
        "run_start_date": None,
        "run_end_date": None,
        "status": SimulationStatus.UNKNOWN.value,
    }

    try:
        lines = _open_text(file_path).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read case status file %s (%s)", file_path, exc)
        return result

    latest_start_index: int | None = None
    latest_start_timestamp: str | None = None

    for index, line in enumerate(lines):
        start_match = CASE_RUN_START_PATTERN.match(line.strip())
        if start_match:
            latest_start_index = index
            latest_start_timestamp = start_match.group("timestamp")

    if latest_start_index is None or latest_start_timestamp is None:
        return result

    result["run_start_date"] = latest_start_timestamp

    for line in lines[latest_start_index + 1 :]:
        terminal_match = CASE_RUN_TERMINAL_PATTERN.match(line.strip())
        if not terminal_match:
            continue

        result["run_end_date"] = terminal_match.group("timestamp")
        result["status"] = (
            SimulationStatus.COMPLETED.value
            if terminal_match.group("state") == "success"
            else SimulationStatus.FAILED.value
        )
        return result

    result["status"] = SimulationStatus.RUNNING.value
    return result
