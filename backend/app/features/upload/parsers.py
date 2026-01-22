import gzip
from datetime import datetime
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


def parse_readme_case(path: Path) -> dict:
    text = _open_text(path)

    for line in text.splitlines():
        if "create_newcase" in line:
            parts = line.split()
            return {
                "res": _arg(parts, "--res"),
                "compset": _arg(parts, "--compset"),
            }

    raise ValueError("README.case missing create_newcase line")


def parse_git_describe(path: Path) -> dict:
    version = _open_text(path).strip()
    if "-g" in version:
        tag, _, rest = version.rpartition("-")
        return {"tag": tag, "hash": rest[1:]}
    return {"tag": version, "hash": None}


def parse_env_case(path: Path) -> str | None:
    text = _open_text(path)
    for line in text.splitlines():
        if "CASE_GROUP" in line:
            return line.split("value=")[-1].strip('"')
    return None


def parse_env_build(path: Path) -> str | None:
    text = _open_text(path)
    for line in text.splitlines():
        if "COMPILER" in line:
            return line.split("value=")[-1].strip('"')
    return None


def _arg(parts, name):
    if name in parts:
        i = parts.index(name)
        return parts[i + 1]
    for p in parts:
        if p.startswith(f"{name}="):
            return p.split("=", 1)[1]
    return None


def _open_text(path: Path) -> str:
    if path.suffix == ".gz":
        return gzip.open(path, "rt").read()

    return path.read_text()
