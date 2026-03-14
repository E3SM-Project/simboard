import gzip
from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.ingestion.parsers.e3sm_timing import _parse_seconds, parse_e3sm_timing

CONTENT_FIXTURE = (
    "LID         : 1081156.251218-200923\n"
    "Curr Date   : Thu Dec 18 20:54:58 2025\n"
    "Init Time   : 124.909 seconds\n"
    "Run Time    : 2599.194 seconds\n"
    "Final Time  : 0.375 seconds\n"
)


class TestE3SMTimingParser:
    @pytest.fixture
    def sample_timing_file(self, tmp_path):
        file_path = tmp_path / "e3sm_timing.txt"
        file_path.write_text(CONTENT_FIXTURE)

        return file_path

    @pytest.fixture
    def sample_gz_timing_file(self, tmp_path):
        file_path = tmp_path / "e3sm_timing.txt.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(CONTENT_FIXTURE)

        return file_path

    def test_parse_plain(self, sample_timing_file):
        data = parse_e3sm_timing(sample_timing_file)

        assert data["execution_id"] == "1081156.251218-200923"
        assert data["run_end_date"] == "2025-12-18T20:54:58"
        assert data["run_start_date"] == "2025-12-18T20:09:33"
        assert "simulation_start_date" not in data

    def test_parse_gz(self, sample_gz_timing_file):
        data = parse_e3sm_timing(sample_gz_timing_file)

        assert data["execution_id"] == "1081156.251218-200923"
        assert data["run_end_date"] == "2025-12-18T20:54:58"
        assert data["run_start_date"] == "2025-12-18T20:09:33"

    def test_missing_init_time_leaves_run_start_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_missing_init.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_end_date"] == "2025-12-18T20:54:58"
        assert data["run_start_date"] is None

    def test_missing_run_time_leaves_run_start_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Init Time   : 124.909 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_missing_run.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_start_date"] is None

    def test_missing_final_time_leaves_run_start_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Init Time   : 124.909 seconds\n"
            "Run Time    : 2599.194 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_missing_final.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_start_date"] is None

    def test_malformed_curr_date_leaves_dates_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Invalid Date Format\n"
            "Init Time   : 124.909 seconds\n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_invalid_date.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_end_date"] is None
        assert data["run_start_date"] is None

    def test_malformed_numeric_timing_values_leave_run_start_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Init Time   : not-a-number\n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_invalid_numeric.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_end_date"] == "2025-12-18T20:54:58"
        assert data["run_start_date"] is None

    def test_read_error_returns_empty_result(self):
        with patch(
            "app.features.ingestion.parsers.e3sm_timing._open_text",
            side_effect=OSError("boom"),
        ):
            data = parse_e3sm_timing(Path("/tmp/missing.txt"))

        assert data == {
            "execution_id": None,
            "run_start_date": None,
            "run_end_date": None,
        }

    def test_missing_curr_date_keeps_run_dates_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Init Time   : 124.909 seconds\n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_missing_curr_date.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["execution_id"] == "1081156.251218-200923"
        assert data["run_end_date"] is None
        assert data["run_start_date"] is None

    def test_missing_lid_returns_none_execution_id(self, tmp_path):
        content = (
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Init Time   : 124.909 seconds\n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_missing_lid.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["execution_id"] is None
        assert data["run_end_date"] == "2025-12-18T20:54:58"

    def test_empty_numeric_field_leaves_run_start_none(self, tmp_path):
        content = (
            "LID         : 1081156.251218-200923\n"
            "Curr Date   : Thu Dec 18 20:54:58 2025\n"
            "Init Time   : \n"
            "Run Time    : 2599.194 seconds\n"
            "Final Time  : 0.375 seconds\n"
        )
        file_path = tmp_path / "e3sm_timing_empty_numeric.txt"
        file_path.write_text(content)

        data = parse_e3sm_timing(file_path)

        assert data["run_end_date"] == "2025-12-18T20:54:58"
        assert data["run_start_date"] is None

    def test_parse_seconds_returns_none_on_float_value_error(self):
        with patch(
            "app.features.ingestion.parsers.e3sm_timing.float",
            side_effect=ValueError("boom"),
            create=True,
        ):
            assert _parse_seconds("12.5 seconds") is None
