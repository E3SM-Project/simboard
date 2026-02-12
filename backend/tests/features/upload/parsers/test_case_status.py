import logging

from app.features.upload.parsers.case_status import parse_case_status


class TestCaseStatusParser:
    def test_extracts_run_start_and_end_date_nmonths(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2015-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=nmonths,STOP_N=41  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["run_start_date"] == "2015-01-01"
        assert result["run_end_date"] == "2018-06-01"  # 41 months after Jan 2015

    def test_extracts_run_start_and_end_date_ndays(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2020-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=ndays,STOP_N=10  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["run_start_date"] == "2020-01-01"
        assert result["run_end_date"] == "2020-01-11"

    def test_extracts_run_start_and_end_date_nyears(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2000-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=nyears,STOP_N=2  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["run_start_date"] == "2000-01-01"
        assert result["run_end_date"] == "2002-01-01"

    def test_missing_fields(self, tmp_path):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE=2015-01-01  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        result = parse_case_status(str(file_path))

        assert result["run_start_date"] == "2015-01-01"
        assert result["run_end_date"] is None

    def test_malformed_lines_log_warning_and_continue(self, tmp_path, caplog):
        content = (
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "RUN_STARTDATE 2015-01-01  </command>\n"
            "2025-12-18 22:36:24: xmlchange success <command> ./xmlchange "
            "STOP_OPTION=ndays,STOP_N=not-a-number  </command>\n"
        )
        file_path = tmp_path / "casestatus.txt"
        file_path.write_text(content)

        logger = logging.getLogger("app.features.upload.parsers.case_status")
        logger.propagate = True
        logger.disabled = False

        with caplog.at_level(
            logging.WARNING, logger="app.features.upload.parsers.case_status"
        ):
            result = parse_case_status(str(file_path))

        assert result["run_start_date"] is None
        assert result["run_end_date"] is None
        assert any("Malformed RUN_STARTDATE" in message for message in caplog.messages)
        assert any(
            "Malformed STOP_OPTION/STOP_N" in message for message in caplog.messages
        )
