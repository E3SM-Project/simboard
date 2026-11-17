import re
from pathlib import Path

from app.core.logger import _setup_custom_logger
from app.features.catalog.enums import ExecutionStatus
from app.features.ingestion.parsers.utils import _open_text

logger = _setup_custom_logger(__name__)

TIMESTAMP_PATTERN = r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
CASE_RUN_START_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+starting(?:\s+\S+)?\s*$"
)
CASE_RUN_TERMINAL_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+case\.run\s+(?P<state>success|error)\b"
)
CASE_STATUS_ENTRY_PATTERN = re.compile(
    rf"^{TIMESTAMP_PATTERN}:\s+(?P<action>\S+\s+\S+)(?:\s+(?P<detail>.*))?$"
)
# CIME resubmits the next job when a run (or short-term archive) succeeds.
RESUBMIT_TRIGGER_ACTIONS = {"case.run success", "st_archive success"}


def parse_case_status(
    file_path: str | Path, *, strict_read: bool = False
) -> dict[str, str | None]:
    """Parse the latest ``case.run`` attempt from ``CaseStatus``.

    ``CaseStatus`` can record multiple attempts for the same execution. The
    latest ``case.run starting`` entry is treated as authoritative and the first
    terminal entry after it determines the run status.

    Set ``strict_read`` to propagate read errors instead of returning ``unknown``.
    """
    file_path = Path(file_path)
    result: dict[str, str | None] = {
        "run_start_date": None,
        "run_end_date": None,
        "status": ExecutionStatus.UNKNOWN.value,
    }

    try:
        lines = _open_text(file_path).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        if strict_read:
            raise
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
            ExecutionStatus.COMPLETED.value
            if terminal_match.group("state") == "success"
            else ExecutionStatus.FAILED.value
        )
        return result

    result["status"] = ExecutionStatus.RUNNING.value
    return result


def parse_case_submit_time(file_path: str | Path, job_id: str) -> str | None:
    """Return when a user submitted ``job_id``'s chain with ``case.submit``.

    A manual submit returns its own time. An automatic resubmit, logged right
    after the previous job's success, returns the manual submit that started the
    chain, so scripts saved later without submitting are excluded; a resubmit
    without a logged manual submit returns ``None``. Times are
    ``YYYYMMDDHHMMSS`` digits, comparable with run-script provenance timestamps
    saved in the same login environment. Read errors return ``None``;
    ``parse_case_status`` already reports them.
    """
    try:
        lines = _open_text(Path(file_path)).splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    chain_start: str | None = None
    submit_time: str | None = None
    resubmit = False
    for line in lines:
        entry = CASE_STATUS_ENTRY_PATTERN.match(line.strip())
        if not entry or entry.group("action") == "case.submit starting":
            continue

        if entry.group("action") == "case.submit success":
            if not resubmit:
                chain_start = re.sub(r"\D", "", entry.group("timestamp"))

            job_ids = {
                token.rsplit(":", 1)[-1].split(".")[0]
                for token in re.split(r"[\s,]+", entry.group("detail") or "")
            }
            if job_id in job_ids:
                submit_time = chain_start

        resubmit = entry.group("action") in RESUBMIT_TRIGGER_ACTIONS

    return submit_time
