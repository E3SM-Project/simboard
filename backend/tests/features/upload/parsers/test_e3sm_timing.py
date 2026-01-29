import gzip

import pytest

from app.features.upload.parsers.e3sm_timing import parse_e3sm_timing


class TestE3SMTimingParser:
    @pytest.fixture
    def sample_timing_file(self, tmp_path):
        """Create a sample E3SM timing file."""
        content = (
            "Case: e3sm_v1_ne30\n"
            "Machine: cori-knl\n"
            "User: test_user\n"
            "LID: 123456\n"
            "Curr Date: Tue Jan 10 12:34:56 2023\n"
            "grid: ne30_oECv3\n"
            "compset: A_WCYCL1850\n"
            "run length: 5 days\n"
            "stop option: ndays\n"
            "stop_n: 5\n"
        )
        file_path = tmp_path / "e3sm_timing.txt"
        file_path.write_text(content)
        return file_path

    @pytest.fixture
    def sample_gz_timing_file(self, tmp_path):
        """Create a sample gzipped E3SM timing file."""

        content = (
            "Case: e3sm_v1_ne30\n"
            "Machine: cori-knl\n"
            "User: test_user\n"
            "LID: 123456\n"
            "Curr Date: Tue Jan 10 12:34:56 2023\n"
            "grid: ne30_oECv3\n"
            "compset: A_WCYCL1850\n"
            "run length: 5 days\n"
            "stop option: ndays\n"
            "stop_n: 5\n"
        )
        file_path = tmp_path / "e3sm_timing.txt.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def test_parse_plain(self, sample_timing_file):
        data = parse_e3sm_timing(sample_timing_file)

        assert data["case"] == "e3sm_v1_ne30"
        assert data["machine"] == "cori-knl"
        assert data["user"] == "test_user"
        assert data["lid"] == "123456"
        assert (
            data["date"].strftime("%a %b %d %H:%M:%S %Y") == "Tue Jan 10 12:34:56 2023"
        )
        assert data["grid_long"] == "ne30_oECv3"
        assert data["compset_long"] == "A_WCYCL1850"
        assert data["run_config"]["stop_option"] == "ndays"
        assert data["run_config"]["stop_n"] == "5"
        assert data["run_config"]["run_length"] == "5 days"

    def test_parse_gz(self, sample_gz_timing_file):
        data = parse_e3sm_timing(sample_gz_timing_file)

        assert data["case"] == "e3sm_v1_ne30"
        assert data["machine"] == "cori-knl"
        assert data["user"] == "test_user"
        assert data["lid"] == "123456"
        assert (
            data["date"].strftime("%a %b %d %H:%M:%S %Y") == "Tue Jan 10 12:34:56 2023"
        )
        assert data["grid_long"] == "ne30_oECv3"
        assert data["compset_long"] == "A_WCYCL1850"
        assert data["run_config"]["stop_option"] == "ndays"
        assert data["run_config"]["stop_n"] == "5"
        assert data["run_config"]["run_length"] == "5 days"

    def test_missing_fields(self, tmp_path):
        content = "Case: e3sm_v1_ne30\nMachine: cori-knl\n"
        file_path = tmp_path / "e3sm_timing_missing.txt"
        file_path.write_text(content)
        data = parse_e3sm_timing(file_path)

        assert data["case"] == "e3sm_v1_ne30"
        assert data["machine"] == "cori-knl"
        assert data["user"] is None
        assert data["lid"] is None
        assert data["date"] is None
        assert data["grid_long"] is None
        assert data["compset_long"] is None
        assert data["run_config"]["stop_option"] is None
        assert data["run_config"]["stop_n"] is None
        assert data["run_config"]["run_length"] is None

    def test_invalid_date(self, tmp_path):
        content = (
            "Case: e3sm_v1_ne30\nMachine: cori-knl\nCurr Date: Invalid Date Format\n"
        )
        file_path = tmp_path / "e3sm_timing_invalid_date.txt"
        file_path.write_text(content)
        data = parse_e3sm_timing(file_path)

        assert data["case"] == "e3sm_v1_ne30"
        assert data["machine"] == "cori-knl"
        assert data["date"] == "Invalid Date Format"
