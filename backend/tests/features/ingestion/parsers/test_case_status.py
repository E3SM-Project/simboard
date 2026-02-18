import logging
from unittest.mock import Mock, patch

from app.features.ingestion.parsers.case_status import (
    _calculate_simulation_end_date,
    _extract_latest_run_metadata,
    _update_simulation_end_date,
    parse_case_status,
)
from app.features.simulation.enums import SimulationStatus


class TestCaseStatusParser:
    def test_returns_default_result_on_read_error(self):
        with patch(
            "app.features.ingestion.parsers.case_status._get_open_func",
            return_value=Mock(side_effect=OSError("boom")),
        ):
            result = parse_case_status("/tmp/missing/casestatus.txt")

        assert result == {
            "simulation_start_date": None,
            "simulation_end_date": None,
            "run_start_date": None,
            "run_end_date": None,
            "status": None,
        }

    def test_extracts_simulation_start_and_end_date_nmonths(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2015-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=nmonths,STOP_N=41  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] == "2015-01-01"
        assert result["simulation_end_date"] == "2018-06-01"  # 41 months after Jan 2015

    def test_extracts_simulation_start_and_end_date_ndays(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2020-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=ndays,STOP_N=10  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] == "2020-01-01"
        assert result["simulation_end_date"] == "2020-01-11"

    def test_extracts_simulation_start_and_end_date_nyears(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2000-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=nyears,STOP_N=2  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] == "2000-01-01"
        assert result["simulation_end_date"] == "2002-01-01"

    def test_missing_fields(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2015-01-01  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] == "2015-01-01"
        assert result["simulation_end_date"] is None

    def test_malformed_lines_log_warning_and_continue(self, tmp_path, caplog):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE 2015-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=ndays,STOP_N=not-a-number  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        logger = logging.getLogger("app.features.ingestion.parsers.case_status")
        old_propagate = logger.propagate
        old_level = logger.level
        logger.propagate = False
        logger.disabled = False
        logger.setLevel(logging.WARNING)

        logger.addHandler(caplog.handler)
        try:
            result = parse_case_status(str(file_path))
        finally:
            logger.removeHandler(caplog.handler)
            logger.propagate = old_propagate
            logger.setLevel(old_level)

        assert result["simulation_start_date"] is None
        assert result["simulation_end_date"] is None
        assert any("Malformed RUN_STARTDATE" in message for message in caplog.messages)
        assert any(
            "Malformed STOP_OPTION/STOP_N" in message for message in caplog.messages
        )

    def test_stop_option_without_start_date_returns_none(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=ndays,STOP_N=10  </command>\n"
        )
        file_path = tmp_path / "casestatus_missing_start.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] is None
        assert result["simulation_end_date"] is None

    def test_unknown_stop_option_returns_none(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2020-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=nhours,STOP_N=10  </command>\n"
        )
        file_path = tmp_path / "casestatus_unknown_stop.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["simulation_start_date"] == "2020-01-01"
        assert result["simulation_end_date"] is None

    def test_extract_latest_run_metadata_sets_completed_status(self):
        lines = [
            "2025-01-01 00:00:00: case.run starting 123\n",
            "2025-01-01 01:00:00: case.run success\n",
        ]
        start_match = Mock()
        start_match.group.return_value = "2025-01-01 00:00:00"
        result = {
            "run_start_date": None,
            "run_end_date": None,
            "status": None,
        }

        _extract_latest_run_metadata(lines, 0, start_match, result)

        assert result["run_start_date"] == "2025-01-01 00:00:00"
        assert result["run_end_date"] == "2025-01-01 01:00:00"
        assert result["status"] == SimulationStatus.COMPLETED.value

    def test_extract_latest_run_metadata_sets_failed_status(self):
        lines = [
            "2025-01-01 00:00:00: case.run starting 123\n",
            "2025-01-01 01:00:00: case.run error\n",
        ]
        start_match = Mock()
        start_match.group.return_value = "2025-01-01 00:00:00"
        result = {
            "run_start_date": None,
            "run_end_date": None,
            "status": None,
        }

        _extract_latest_run_metadata(lines, 0, start_match, result)

        assert result["status"] == SimulationStatus.FAILED.value

    def test_extract_latest_run_metadata_sets_running_without_terminal_state(self):
        lines = [
            "2025-01-01 00:00:00: case.run starting 123\n",
            "noise line\n",
        ]
        start_match = Mock()
        start_match.group.return_value = "2025-01-01 00:00:00"
        result = {
            "run_start_date": None,
            "run_end_date": None,
            "status": None,
        }

        _extract_latest_run_metadata(lines, 0, start_match, result)

        assert result["run_start_date"] == "2025-01-01 00:00:00"
        assert result["run_end_date"] is None
        assert result["status"] == SimulationStatus.RUNNING.value

    def test_extract_latest_run_metadata_no_start_match_no_changes(self):
        result = {
            "run_start_date": None,
            "run_end_date": None,
            "status": None,
        }

        _extract_latest_run_metadata([], None, None, result)

        assert result["run_start_date"] is None
        assert result["run_end_date"] is None
        assert result["status"] is None

    def test_update_simulation_end_date_logs_and_returns_on_invalid_stop_n(self):
        stop_match = Mock()
        stop_match.group.side_effect = lambda key: {
            "stop_option": "ndays",
            "stop_n": "not-an-int",
        }[key]
        result = {"simulation_start_date": "2020-01-01", "simulation_end_date": None}

        _update_simulation_end_date(
            "/tmp/casestatus.txt",
            "STOP_OPTION=ndays,STOP_N=not-an-int",
            stop_match,
            result,
        )

        assert result["simulation_end_date"] is None

    def test_calculate_simulation_end_date_invalid_start_date_returns_none(self):
        assert _calculate_simulation_end_date("invalid-date", "ndays", 3) is None

    def test_parse_case_status_tracks_latest_case_run_start(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: case.run starting 111\n"
            "2025-12-18 23:36:24: case.run error\n"
            "2025-12-19 00:36:24: case.run starting 222\n"
            "2025-12-19 01:36:24: case.run success\n"
        )
        file_path = tmp_path / "casestatus_with_retries.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["run_start_time"] == "2025-12-19 00:36:24"
        assert result["run_end_time"] == "2025-12-19 01:36:24"
        assert result["status"] == SimulationStatus.COMPLETED.value
