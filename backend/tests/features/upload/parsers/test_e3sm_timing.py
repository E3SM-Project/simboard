import gzip

import pytest

from app.features.upload.parsers.e3sm_timing import parse_e3sm_timing

CONTENT_FIXTURE = (
    "Case: e3sm_v1_ne30\n"
    "Machine: cori-knl\n"
    "User: test_user\n"
    "LID: 123456\n"
    "Curr Date: Tue Jan 10 12:34:56 2023\n"
    "grid: ne30_oECv3\n"
    "compset: A_WCYCL1850\n"
    "run length: 42 days (42.0 for ocean)\n"
    "run type: branch, continue_run = TRUE (inittype = FALSE)\n"
    "stop option: ndays\n"
    "stop_n: 5\n"
)


class TestE3SMTimingParser:
    @pytest.fixture
    def sample_timing_file(self, tmp_path):
        """Create a sample E3SM timing file."""
        file_path = tmp_path / "e3sm_timing.txt"
        file_path.write_text(CONTENT_FIXTURE)

        return file_path

    @pytest.fixture
    def sample_gz_timing_file(self, tmp_path):
        """Create a sample gzipped E3SM timing file."""
        file_path = tmp_path / "e3sm_timing.txt.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(CONTENT_FIXTURE)

        return file_path

    def test_parse_plain(self, sample_timing_file):
        data = parse_e3sm_timing(sample_timing_file)

        assert data["case_name"] == "e3sm_v1_ne30"
        assert data["campaign"] is None
        assert data["machine"] == "cori-knl"
        assert data["user"] == "test_user"
        assert data["lid"] == "123456"
        assert data["simulation_start_date"] == "2023-01-10T12:34:56"
        assert data["grid_resolution"] == "ne30_oECv3"
        assert data["compset_alias"] == "A_WCYCL1850"
        assert data["initialization_type"] == "branch"
        assert data["run_config"]["stop_option"] == "ndays"
        assert data["run_config"]["stop_n"] == "5"
        assert data["run_config"]["run_length"] == "42 days (42.0 for ocean)"

    def test_parse_gz(self, sample_gz_timing_file):
        data = parse_e3sm_timing(sample_gz_timing_file)

        assert data["case_name"] == "e3sm_v1_ne30"
        assert data["campaign"] is None
        assert data["machine"] == "cori-knl"
        assert data["user"] == "test_user"
        assert data["lid"] == "123456"
        assert data["simulation_start_date"] == "2023-01-10T12:34:56"
        assert data["grid_resolution"] == "ne30_oECv3"
        assert data["compset_alias"] == "A_WCYCL1850"
        assert data["initialization_type"] == "branch"
        assert data["run_config"]["stop_option"] == "ndays"
        assert data["run_config"]["stop_n"] == "5"
        assert data["run_config"]["run_length"] == "42 days (42.0 for ocean)"

    def test_missing_fields(self, tmp_path):
        content = "Case: e3sm_v1_ne30\nMachine: cori-knl\n"
        file_path = tmp_path / "e3sm_timing_missing.txt"
        file_path.write_text(content)
        data = parse_e3sm_timing(file_path)

        assert data["case_name"] == "e3sm_v1_ne30"
        assert data["campaign"] is None
        assert data["machine"] == "cori-knl"
        assert data["user"] is None
        assert data["lid"] is None
        assert data["simulation_start_date"] is None
        assert data["grid_resolution"] is None
        assert data["compset_alias"] is None
        assert data["initialization_type"] is None
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

        assert data["case_name"] == "e3sm_v1_ne30"
        assert data["campaign"] is None
        assert data["machine"] == "cori-knl"
        assert data["simulation_start_date"] == "Invalid Date Format"

    def test_campaign_and_experiment_type_from_case_name(self, tmp_path):
        content = (
            "Case: v3.LR.historical_0121\n"
            "Machine: cori-knl\n"
            "Curr Date: Tue Jan 10 12:34:56 2023\n"
        )
        file_path = tmp_path / "e3sm_timing_campaign.txt"
        file_path.write_text(content)
        data = parse_e3sm_timing(file_path)

        assert data["campaign"] == "v3.LR.historical"
        assert data["experiment_type"] == "historical"

    def test_stop_option_and_stop_n_same_line(self, tmp_path):
        content = (
            "Case: e3sm_v1_ne30\nMachine: cori-knl\nstop option: ndays, stop_n=7\n"
        )
        file_path = tmp_path / "e3sm_timing_stop_line.txt"
        file_path.write_text(content)
        data = parse_e3sm_timing(file_path)

        assert data["run_config"]["stop_option"] == "ndays"
        assert data["run_config"]["stop_n"] == "7"
