import gzip
from pathlib import Path


def _open_text(path: Path) -> str:
    """
    Open a file (plain or gzipped) and return its text content.

    Parameters
    ----------
    path : Path
        Path to the file.

    Returns
    -------
    str
        File contents as a string.
    """
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    else:
        with open(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()


def _get_open_func(file_path: str):
    """
    Return the appropriate open function for a file, using gzip.open for .gz files.
    """
    if file_path.endswith(".gz"):
        return gzip.open

    return open
