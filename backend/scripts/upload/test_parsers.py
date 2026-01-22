from pathlib import Path

from app.features.upload.parsers import (
    parse_e3sm_timing,
    parse_git_describe,
    parse_readme_case,
)

path = Path(
    "exp_archive/1085209.251220-105556/e3sm_timing.v3.LR.historical_0121.1085209.251220-105556.gz"
)
data = parse_e3sm_timing(path)

assert data["case"] == "e3sm_v1_ne30"
assert data["machine"] == "cori-knl"
assert data["user"] is not None
assert data["date"] is not None
