import re
from pathlib import Path

from app.features.upload.parsers.utils import _open_text


def parse_readme_case(path: str | Path) -> dict[str, str | None]:
    """
    Parse a README.case file and extract creation date, resolution, and compset.

    Parameters
    ----------
    path : str or Path
        Path to the README.case file (plain text or .gz).

    Returns
    -------
    dict[str, str | None]
        Dictionary with keys: 'creation_date', 'res', 'compset'.
    """
    path = Path(path)
    text = _open_text(path)
    lines = text.splitlines()

    creation_date = _extract_timestamp(lines)
    grid_name = _extract_flag_value(lines, "--res")
    compset = _extract_flag_value(lines, "--compset")

    return {"creation_date": creation_date, "grid_name": grid_name, "compset": compset}


def _extract_timestamp(lines: list[str]) -> str | None:
    """
    Extract the timestamp from the first line (format: YYYY-MM-DD HH:MM:SS: ...)
    """
    if lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[0])

        if m:
            return m.group(1)

    return None


def _extract_flag_value(lines: list[str], flag: str) -> str | None:
    """
    Extract a value for a given flag (e.g., --res) from the create_newcase
    command line.

    Parameters
    ----------
    lines : list of str
        Lines from the README.case file.
    flag : str
        The flag to search for (e.g., '--res').

    Returns
    -------
    str or None
        The value for the flag, or None if not found.
    """
    for line in lines:
        if "create_newcase" in line:
            parts = line.strip().split()

            for i, part in enumerate(parts):
                if part == flag:
                    if i + 1 < len(parts):
                        return parts[i + 1]
                elif part.startswith(flag + "="):
                    return part.split("=", 1)[1]

    return None
