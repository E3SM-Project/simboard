import gzip

import pytest

from app.features.ingestion.parsers.cpl_log import parse_cpl_log

# Driver excerpt from OLD_PERF/v3.LR.piClim-histGHG_0201/
# 729179.250417-002844/cpl.log.729179.250417-002844, lines 287–291.
DRIVER_CLOCK = """
(seq_timemgr_clockPrint) Clock = drv            1
(seq_timemgr_clockPrint)   Start Time  =     18500101   00000
(seq_timemgr_clockPrint)   Curr Time   =     20190101   00000
(seq_timemgr_clockPrint)   Ref Time    =     18500101   00000
(seq_timemgr_clockPrint)   Stop Time   =     20200101   00000
"""


@pytest.mark.parametrize("compressed", [False, True])
def test_initial_driver_dates(tmp_path, compressed):
    path = tmp_path / ("cpl.log.lid.gz" if compressed else "cpl.log.lid")
    component = DRIVER_CLOCK.replace("drv", "atm").replace("20190101", "19000101")
    later_driver = DRIVER_CLOCK.replace("20190101", "20191231")
    text = component + DRIVER_CLOCK + component + later_driver
    text += "(seq_mct_drv): at YMD,TOD = 20210101 0\n"
    if compressed:
        with gzip.open(path, "wt") as stream:
            stream.write(text)
    else:
        path.write_text(text)
    assert parse_cpl_log(path) == {
        "simulation_start_date": "2019-01-01",
        "simulation_end_date": "2020-01-01",
    }


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", {}),
        (DRIVER_CLOCK.replace("drv", "atm"), {}),
        (
            DRIVER_CLOCK.replace("20190101", "20191301"),
            {"simulation_end_date": "2020-01-01"},
        ),
        (
            DRIVER_CLOCK.replace("20200101", "bad"),
            {"simulation_start_date": "2019-01-01"},
        ),
        (DRIVER_CLOCK.replace("20200101", "20180101"), {}),
        (DRIVER_CLOCK.split("   Curr Time")[0], {}),
        (
            DRIVER_CLOCK.replace("20190101", "02010101"),
            {
                "simulation_start_date": "0201-01-01",
                "simulation_end_date": "2020-01-01",
            },
        ),
    ],
)
def test_incomplete_or_invalid_clock(tmp_path, text, expected):
    path = tmp_path / "cpl.log.lid"
    path.write_text(text)
    assert parse_cpl_log(path) == expected


def test_missing_file(tmp_path):
    assert parse_cpl_log(tmp_path / "missing") == {}


def test_corrupt_gzip(tmp_path):
    path = tmp_path / "cpl.log.lid.gz"
    path.write_bytes(b"not gzip")
    assert parse_cpl_log(path) == {}


def test_damaged_deflate_payload(tmp_path):
    path = tmp_path / "cpl.log.lid.gz"
    # Valid gzip header followed by a reserved deflate block type (BTYPE=3).
    path.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8)
    assert parse_cpl_log(path) == {}
