import xml.etree.ElementTree as ET
from pathlib import Path

from app.features.upload.parsers.utils import _open_text


def parse_env_case(env_case_path: str | Path) -> dict[str, str | None]:
    """Parse env_case.xml (plain or gzipped) to extract group_name.

    Parameters
    ----------
    env_case_path : str or Path
        Path to the env_case.xml file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with key 'group_name' (str or None)
    """
    env_case_path = Path(env_case_path)
    group_name = _extract_value_from_file(env_case_path, "CASE_GROUP")

    return {"group_name": group_name}


def parse_env_build(env_build_path: str | Path) -> dict[str, str | None]:
    """Parse env_build.xml (plain or gzipped) to extract compiler and mpilib.

    Parameters
    ----------
    env_build_path : str or Path
        Path to the env_build.xml file (plain or .gz)

    Returns
    -------
    dict
        Dictionary with keys 'compiler', 'mpilib' (str or None)
    """
    env_build_path = Path(env_build_path)
    compiler = _extract_value_from_file(env_build_path, "COMPILER")
    mpilib = _extract_value_from_file(env_build_path, "MPILIB")

    return {"compiler": compiler, "mpilib": mpilib}


def _extract_value_from_file(path: Path, entry_id: str) -> str | None:
    """Extract the value of a specific entry from an XML file.

    Parameters
    ----------
    path : Path
        Path to the XML file (plain or .gz)
    entry_id : str
        The ID of the entry to extract

    Returns
    -------
    str | None
        The value of the entry, or None if not found
    """
    text = _open_text(path)

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    return _find_entry_value(root, entry_id)


def _find_entry_value(root, entry_id: str) -> str | None:
    """
    Search for <entry id="..." value="..." /> or <entry id="...">text</entry>.

    Parameters
    ----------
    root : Element
        The root element of the XML tree
    entry_id : str
        The ID of the entry to find

    Returns
    -------
    str | None
        The value of the entry, or None if not found
    """
    for entry in root.iter("entry"):
        if entry.attrib.get("id") == entry_id:
            # Prefer value attribute if present
            if "value" in entry.attrib:
                return entry.attrib["value"]

            # Otherwise, use text content if present and non-empty
            if entry.text and entry.text.strip():
                return entry.text.strip()

    return None
