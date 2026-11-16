import re
import shlex
from pathlib import Path

from app.features.ingestion.parsers.utils import _open_text


def parse_readme_case(path: str | Path) -> dict[str, str | None]:
    """
    Parse a README.case file and extract creation date, grid alias, and compset alias.

    Parameters
    ----------
    path : str or Path
        Path to the README.case file (plain text or .gz).

    Returns
    -------
    dict[str, str | None]
        Dictionary with keys: 'creation_date', 'grid_alias', 'compset_alias'.
    """
    path = Path(path)
    text = _open_text(path)
    lines = text.splitlines()

    creation_date = _extract_timestamp(lines)
    grid_alias = _extract_flag_value(lines, "--res", "-res")
    compset = _extract_flag_value(lines, "--compset", "-compset")
    # CIME's config_compsets.xsd defines aliases as XML NCNames. Long names
    # start with a time specifier (e.g. 1850/20TR) or use colon-labelled
    # components, and may contain percent modifiers. Underscores alone do not
    # distinguish aliases from long names.
    compset_alias = (
        compset
        if compset and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", compset)
        else None
    )

    return {
        "creation_date": creation_date,
        "grid_alias": grid_alias,
        "compset_alias": compset_alias,
    }


def _extract_timestamp(lines: list[str]) -> str | None:
    """
    Extract the timestamp from the first line (format: YYYY-MM-DD HH:MM:SS: ...)
    """
    if lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[0])

        if m:
            return m.group(1)

    return None


def _extract_flag_value(lines: list[str], *flags: str) -> str | None:
    """
    Extract a value for a given flag (e.g., --res) from the create_newcase
    command line.

    Parameters
    ----------
    lines : list of str
        Lines from the README.case file.
    flags : str
        Accepted spellings of the flag (e.g., '--res').

    Returns
    -------
    str or None
        The value for the flag, or None if not found.
    """
    for line in lines:
        if "create_newcase" in line:
            try:
                parts = shlex.split(line)
            except ValueError:
                continue

            for i, part in enumerate(parts):
                if part in flags:
                    if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                        return parts[i + 1] or None
                elif any(part.startswith(flag + "=") for flag in flags):
                    return part.split("=", 1)[1] or None

    return None
