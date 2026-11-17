import gzip
from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.ingestion.parsers.case_status import (
    parse_case_status,
    parse_case_submit_time,
)


class TestCaseStatusParser:
    def test_returns_unknown_status_on_read_error(self) -> None:
        with (
            patch(
                "app.features.ingestion.parsers.case_status._open_text",
                side_effect=OSError("boom"),
            ),
            patch(
                "app.features.ingestion.parsers.case_status.logger.warning"
            ) as mock_warning,
        ):
            result = parse_case_status(Path("/tmp/missing/CaseStatus.001.gz"))

        assert result == {
            "run_start_date": None,
            "run_end_date": None,
            "status": "unknown",
        }
        mock_warning.assert_called_once()

    @pytest.mark.parametrize(
        "error",
        [OSError("boom"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")],
    )
    def test_strict_read_propagates_errors(self, monkeypatch, error) -> None:
        def unreadable(path):
            raise error

        monkeypatch.setattr(
            "app.features.ingestion.parsers.case_status._open_text", unreadable
        )

        with pytest.raises(type(error)):
            parse_case_status("CaseStatus.001.gz", strict_read=True)

    def test_extracts_completed_status_from_latest_attempt(self, tmp_path) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text(
            "\n".join(
                [
                    "2025-01-01 00:00:00: case.run starting 111",
                    "2025-01-01 01:00:00: case.run error",
                    "2025-01-01 02:00:00: case.run starting 222",
                    "2025-01-01 03:00:00: case.run success",
                ]
            )
        )

        result = parse_case_status(case_status)

        assert result["run_start_date"] == "2025-01-01 02:00:00"
        assert result["run_end_date"] == "2025-01-01 03:00:00"
        assert result["status"] == "completed"

    def test_extracts_failed_status(self, tmp_path) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text(
            "\n".join(
                [
                    "2025-01-01 00:00:00: case.run starting 111",
                    "2025-01-01 01:00:00: case.run error",
                ]
            )
        )

        result = parse_case_status(case_status)

        assert result["run_end_date"] == "2025-01-01 01:00:00"
        assert result["status"] == "failed"

    def test_extracts_running_status_without_terminal_entry(self, tmp_path) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text(
            "\n".join(
                [
                    "2025-01-01 00:00:00: case.run starting 111",
                    "2025-01-01 00:10:00: unrelated log line",
                ]
            )
        )

        result = parse_case_status(case_status)

        assert result["run_start_date"] == "2025-01-01 00:00:00"
        assert result["run_end_date"] is None
        assert result["status"] == "running"

    @pytest.mark.parametrize("strict_read", [False, True])
    def test_returns_unknown_status_without_case_run_entries(
        self, tmp_path, strict_read
    ) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text("2025-01-01 00:00:00: xmlchange success")

        result = parse_case_status(case_status, strict_read=strict_read)

        assert result["run_start_date"] is None
        assert result["run_end_date"] is None
        assert result["status"] == "unknown"


class TestCaseSubmitTime:
    @pytest.mark.parametrize(
        "lines,expected",
        [
            (["2025-03-19 11:38:00: case.submit success 37013148"], "20250319113800"),
            (
                [
                    "2025-03-19 11:20:00: case.submit success 37013148",
                    "2025-03-19 11:38:00: case.submit success 37013148",
                ],
                "20250319113800",
            ),
            (
                ["2025-03-19 11:38:00: case.submit success 1, 37013148"],
                "20250319113800",
            ),
            (
                ["2025-03-19 11:38:00: case.submit success 37013148.pbs"],
                "20250319113800",
            ),
            (
                [
                    "2025-03-19 11:38:00: case.submit success "
                    "case.run:37013148, case.st_archive:37013149"
                ],
                "20250319113800",
            ),
            (
                [
                    "2025-03-19 11:38:00: case.submit success 100",
                    " ---------------------------------------------------",
                    "2025-03-19 11:40:00: xmlchange success <command> ./xmlchange "
                    "STOP_N=1 </command>",
                    "2025-03-20 08:00:00: case.run success 100",
                    " ---------------------------------------------------",
                    "2025-03-20 08:00:10: case.submit starting 200",
                    "2025-03-20 08:00:10: case.submit success 200",
                    "2025-03-21 08:00:00: case.run success 200",
                    "2025-03-21 08:00:10: case.submit starting 37013148",
                    "2025-03-21 08:00:10: case.submit success 37013148",
                ],
                "20250319113800",
            ),
            (
                [
                    "2025-03-19 11:38:00: case.submit success 100",
                    "2025-03-20 08:00:00: case.run success 100",
                    "2025-03-20 09:00:00: xmlchange success <command> ./xmlchange "
                    "STOP_N=1 </command>",
                    "2025-03-20 09:00:10: case.submit success 37013148",
                ],
                "20250320090010",
            ),
            (
                [
                    "2025-03-20 08:00:00: case.run success 100",
                    "2025-03-20 08:00:10: case.submit success 37013148",
                ],
                None,
            ),
            (
                [
                    "2025-03-19 11:38:00: case.submit success 100",
                    "2025-03-20 08:00:00: st_archive success ",
                    "2025-03-20 08:00:10: case.submit success 37013148",
                ],
                "20250319113800",
            ),
            (
                [
                    "2025-03-19 11:38:00: case.submit success 100",
                    "2025-03-20 08:00:00: case.run error ",
                    "ERROR:  missing restart file",
                    " ---------------------------------------------------",
                    "2025-03-20 09:00:10: case.submit success 37013148",
                ],
                "20250320090010",
            ),
            (["2025-03-19 11:38:00: case.submit success"], None),
            (["2025-03-19 11:38:00: case.submit success 370131480"], None),
            (["2025-03-19 11:38:00: case.submit starting 37013148"], None),
            (["2025-03-19 11:38:00: case.submit error 37013148"], None),
            ([], None),
        ],
    )
    def test_returns_latest_successful_submit_for_job(
        self, tmp_path, lines, expected
    ) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text("\n".join(lines))

        assert parse_case_submit_time(case_status, "37013148") == expected

    def test_returns_none_on_read_error(self, tmp_path) -> None:
        assert parse_case_submit_time(tmp_path / "missing", "37013148") is None

    @pytest.mark.parametrize(
        "script_times,expected",
        [((), "20250319113800"), (("20250322090000",), "20250322090010")],
    )
    def test_script_saved_after_run_success_marks_manual_submit(
        self, tmp_path, script_times, expected
    ) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text(
            "2025-03-19 11:38:00: case.submit success 100\n"
            "2025-03-21 08:00:00: case.run success 100\n"
            "2025-03-22 09:00:10: case.submit success 37013148\n"
        )

        assert parse_case_submit_time(case_status, "37013148", script_times) == expected

    def test_truncated_gzip_is_treated_as_unreadable(self, tmp_path) -> None:
        case_status = tmp_path / "CaseStatus.001.gz"
        with gzip.open(case_status, "wt") as stream:
            stream.write("2025-03-19 11:38:00: case.submit success 37013148\n" * 50)
        case_status.write_bytes(case_status.read_bytes()[:-12])

        assert parse_case_submit_time(case_status, "37013148") is None
        assert parse_case_status(case_status)["status"] == "unknown"
