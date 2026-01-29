import glob
import gzip
import os
from pathlib import Path


def validate_e3sm_experiment(exp_dir):
    required = [
        "e3sm_timing.*",
        "timing.*.tar.gz",
        "README.case.*",
        "GIT_DESCRIBE.*",
        "CaseStatus.*",
        "CaseDocs.*/",
    ]

    for pattern in required:
        if not glob.glob(os.path.join(exp_dir, pattern)):
            raise OSError(f"Missing required file: {pattern}")


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
