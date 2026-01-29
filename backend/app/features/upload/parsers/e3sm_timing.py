import gzip
import os
from datetime import datetime
from glob import glob
from pathlib import Path


def parse_e3sm_timing(path: Path) -> dict:
    text = _open_text(path)

    def find(prefix):
        for line in text.splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
        return None

    return {
        "case": find("Case"),
        "machine": find("Machine"),
        "user": find("User"),
        "lid": find("LID"),
        "date": datetime.strptime(find("Curr Date"), "%a %b %d %H:%M:%S %Y"),
        "grid_long": find("grid"),
        "compset_long": find("compset"),
        "run_config": {
            "stop_option": find("stop option"),
            "stop_n": find("stop_n"),
        },
    }
