from pathlib import Path
from unittest.mock import patch

from app.features.ingestion.parsers.case_status import parse_case_status


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

    def test_returns_unknown_status_without_case_run_entries(self, tmp_path) -> None:
        case_status = tmp_path / "CaseStatus.001"
        case_status.write_text("2025-01-01 00:00:00: xmlchange success")

        result = parse_case_status(case_status)

        assert result["run_start_date"] is None
        assert result["run_end_date"] is None
        assert result["status"] == "unknown"
