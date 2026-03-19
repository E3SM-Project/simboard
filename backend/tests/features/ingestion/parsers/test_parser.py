"""Integration tests for the parser module focusing on public API."""

import gzip
import io
import os
import tarfile
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest

from app.features.ingestion.parsers import parser
from app.features.ingestion.parsers.types import ParsedSimulation


class TestMainParser:
    @staticmethod
    def _create_execution_metadata_files(
        execution_dir: Path,
        version: str,
        *,
        include_env_run: bool = True,
        include_timing: bool = True,
        case_status_content: str | None = None,
    ) -> None:
        """Create standard execution files for testing."""
        version_base = version.split(".")[0]

        if include_timing:
            timing_file = execution_dir / f"e3sm_timing.{version}"
            timing_file.write_text("timing data")

        if case_status_content is not None:
            with gzip.open(execution_dir / f"CaseStatus.{version_base}.gz", "wt") as f:
                f.write(case_status_content)

        casedocs = execution_dir / "CaseDocs"
        casedocs.mkdir(exist_ok=True)

        with gzip.open(casedocs / f"README.case.{version_base}.gz", "wt") as f:
            f.write("readme content")
        with gzip.open(casedocs / f"env_case.xml.{version_base}.gz", "wt") as f:
            f.write('<config><entry id="CASE" value="test_case" /></config>')
        with gzip.open(casedocs / f"env_build.xml.{version_base}.gz", "wt") as f:
            f.write('<config><entry id="COMPILER" value="gnu" /></config>')

        if include_env_run:
            with gzip.open(casedocs / f"env_run.xml.{version_base}.gz", "wt") as f:
                f.write('<config><entry id="RUN_TYPE" value="startup" /></config>')

        with gzip.open(execution_dir / f"GIT_DESCRIBE.{version_base}.gz", "wt") as f:
            f.write("describe content")

    @staticmethod
    def _create_optional_files(execution_dir: Path, version: str) -> None:
        version_base = version.split(".")[0] if "." in version else version

        with gzip.open(execution_dir / f"GIT_CONFIG.{version_base}.gz", "wt") as f:
            f.write("https://github.com/test/repo")
        with gzip.open(execution_dir / f"GIT_STATUS.{version_base}.gz", "wt") as f:
            f.write("main")

    @staticmethod
    def _create_zip_archive(base_dir: Path, archive_path: Path) -> None:
        zip_file = zipfile.ZipFile(archive_path, "w")

        for root, _dirs, files_list in os.walk(str(base_dir)):
            for file in files_list:
                file_path = Path(root) / file
                arcname = str(file_path.relative_to(str(base_dir)))
                zip_file.write(file_path, arcname)

        zip_file.close()

    @staticmethod
    def _create_tar_gz_archive(base_dir: Path, archive_path: Path) -> None:
        tar_file = tarfile.open(archive_path, "w:gz")

        for root, _dirs, files_list in os.walk(str(base_dir)):
            for file in files_list:
                file_path = Path(root) / file
                arcname = str(file_path.relative_to(str(base_dir)))
                tar_file.add(file_path, arcname=arcname)

        tar_file.close()

    @contextmanager
    def _mock_all_parsers(self, **kwargs: Any) -> Generator[None, None, None]:
        defaults = {
            "parse_env_case": {
                "case_name": "test_case",
                "campaign": "test",
                "machine": "test",
            },
            "parse_env_build": {"compiler": "gnu"},
            "parse_env_run": {"simulation_start_date": "2020-01-01"},
            "parse_readme_case": {},
            "parse_case_status": {"status": "completed"},
            "parse_e3sm_timing": {
                "execution_id": "1081156.251218-200923",
                "run_start_date": "2025-12-18T20:09:33",
                "run_end_date": "2025-12-18T20:54:58",
            },
            "parse_git_describe": {},
            "parse_git_config": None,
            "parse_git_status": None,
        }
        defaults.update(kwargs)

        original_file_specs = deepcopy(parser.FILE_SPECS)

        try:
            parser.FILE_SPECS["case_docs_env_case"]["parser"] = lambda _path: defaults[
                "parse_env_case"
            ]
            parser.FILE_SPECS["case_docs_env_build"]["parser"] = lambda _path: defaults[
                "parse_env_build"
            ]
            parser.FILE_SPECS["case_docs_env_run"]["parser"] = lambda _path: defaults[
                "parse_env_run"
            ]
            parser.FILE_SPECS["readme_case"]["parser"] = lambda _path: defaults[
                "parse_readme_case"
            ]
            parser.FILE_SPECS["case_status"]["parser"] = lambda _path: defaults[
                "parse_case_status"
            ]
            parser.FILE_SPECS["e3sm_timing"]["parser"] = lambda _path: defaults[
                "parse_e3sm_timing"
            ]
            parser.FILE_SPECS["git_describe"]["parser"] = lambda _path: defaults[
                "parse_git_describe"
            ]
            parser.FILE_SPECS["git_config"]["parser"] = lambda _path: (
                defaults["parse_git_config"]
                if isinstance(defaults["parse_git_config"], dict)
                else (
                    {"git_repository_url": defaults["parse_git_config"]}
                    if defaults["parse_git_config"]
                    else {}
                )
            )
            parser.FILE_SPECS["git_status"]["parser"] = lambda _path: (
                defaults["parse_git_status"]
                if isinstance(defaults["parse_git_status"], dict)
                else (
                    {"git_branch": defaults["parse_git_status"]}
                    if defaults["parse_git_status"]
                    else {}
                )
            )

            yield
        finally:
            parser.FILE_SPECS.clear()
            parser.FILE_SPECS.update(original_file_specs)

    def test_file_specs_include_case_status_and_env_run(self) -> None:
        assert "case_status" in parser.FILE_SPECS
        assert "case_docs_env_run" in parser.FILE_SPECS
        assert "e3sm_timing" in parser.FILE_SPECS
        assert parser.FILE_SPECS["case_status"]["required"] is False
        assert parser.FILE_SPECS["case_docs_env_run"]["required"] is True
        assert parser.FILE_SPECS["e3sm_timing"]["required"] is True

    def test_resolve_execution_id_rejects_blank_values(self) -> None:
        with pytest.raises(
            FileNotFoundError,
            match="Required timing-file LID missing for execution directory '1.0-0'",
        ):
            parser._resolve_execution_id("   ", "1.0-0")

    def test_with_valid_zip_archive(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        archive_path = tmp_path / "archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) > 0
        assert skipped == 0
        assert isinstance(result[0], ParsedSimulation)
        assert any("1.0-0" in parsed.execution_dir for parsed in result)

    def test_with_tar_gz_archive(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "2.5-10"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "002.002")

        archive_path = tmp_path / "archive.tar.gz"
        self._create_tar_gz_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) > 0
        assert skipped == 0
        assert any("2.5-10" in parsed.execution_dir for parsed in result)

    def test_with_multiple_executions(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        archive_base.mkdir()

        exec_dir1 = archive_base / "1.0-0"
        exec_dir1.mkdir(parents=True)
        self._create_execution_metadata_files(exec_dir1, "001.001")

        exec_dir2 = archive_base / "2.0-0"
        exec_dir2.mkdir(parents=True)
        self._create_execution_metadata_files(exec_dir2, "002.002")

        archive_path = tmp_path / "multi_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) == 2
        assert skipped == 0

    def test_with_nested_executions(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "parent" / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        archive_path = tmp_path / "nested_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) > 0
        assert skipped == 0

    def test_missing_required_files_skips_incomplete_run(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "1.0-0"
        execution_dir.mkdir(parents=True)
        (execution_dir / "dummy.txt").write_text("dummy")

        archive_path = tmp_path / "bad_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        result, skipped = parser.main_parser(archive_path, extract_dir)

        assert result == []
        assert skipped == 1

    def test_multiple_matching_timing_files_raises_error(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "1.0-0"
        execution_dir.mkdir(parents=True)

        (execution_dir / "e3sm_timing.001.001").write_text("timing1")
        (execution_dir / "e3sm_timing.002.002").write_text("timing2")

        casedocs = execution_dir / "CaseDocs"
        casedocs.mkdir()
        with gzip.open(casedocs / "README.case.001.gz", "wt") as f:
            f.write("readme")
        with gzip.open(casedocs / "env_case.xml.001.gz", "wt") as f:
            f.write('<config><entry id="CASE" value="test_case" /></config>')
        with gzip.open(casedocs / "env_build.xml.001.gz", "wt") as f:
            f.write('<config><entry id="COMPILER" value="gnu" /></config>')
        with gzip.open(execution_dir / "GIT_DESCRIBE.001.gz", "wt") as f:
            f.write("describe")

        archive_path = tmp_path / "duplicate_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="Multiple files matching pattern"):
            parser.main_parser(archive_path, extract_dir)

    def test_unsupported_archive_format_raises_error(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "archive.rar"
        archive_path.write_text("not a real archive")

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="Unsupported archive format"):
            parser.main_parser(str(archive_path), extract_dir)

    def test_no_case_directories_raises_error(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        archive_base.mkdir()
        (archive_base / "some_other_dir").mkdir()
        (archive_base / "some_other_dir" / "file.txt").write_text("data")

        archive_path = tmp_path / "empty_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(
            FileNotFoundError, match="No cases or execution directories found"
        ):
            parser.main_parser(archive_path, extract_dir)

    def test_with_optional_files(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")
        self._create_optional_files(execution_dir, "001")

        archive_path = tmp_path / "with_optional.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers(
            parse_git_config="https://github.com/test/repo",
            parse_git_status="main",
        ):
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) > 0
        assert skipped == 0

    def test_missing_env_run_skips_incomplete_run(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        execution_dir = archive_base / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(
            execution_dir,
            "001.001",
            include_env_run=False,
        )

        archive_path = tmp_path / "missing_env_run.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        result, skipped = parser.main_parser(archive_path, extract_dir)

        assert result == []
        assert skipped == 1

    def test_case_status_is_merged(self, tmp_path: Path) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(
            execution_dir,
            "001.001",
            case_status_content="2025-01-01 00:00:00: case.run error",
        )

        with self._mock_all_parsers(parse_case_status={"status": "failed"}):
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert skipped == 0
        assert result[0].status == "failed"

    def test_case_status_run_dates_override_timing_dates(self, tmp_path: Path) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(
            execution_dir,
            "001.001",
            case_status_content="2025-01-01 00:00:00: case.run error",
        )

        with self._mock_all_parsers(
            parse_case_status={
                "run_start_date": "2025-01-01 00:00:00",
                "run_end_date": None,
                "status": "running",
            },
            parse_e3sm_timing={
                "execution_id": "1081156.251218-200923",
                "run_start_date": "2025-12-18T20:09:33",
                "run_end_date": "2025-12-18T20:54:58",
            },
        ):
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert skipped == 0
        assert result[0].status == "running"
        assert result[0].run_start_date == "2025-01-01 00:00:00"
        assert result[0].run_end_date is None

    def test_missing_case_status_defaults_status_to_unknown(
        self, tmp_path: Path
    ) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert skipped == 0
        assert result[0].status == "unknown"

    def test_missing_timing_lid_skips_incomplete_run(self, tmp_path: Path) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        with self._mock_all_parsers(
            parse_e3sm_timing={
                "execution_id": None,
                "run_start_date": "2025-12-18T20:09:33",
                "run_end_date": "2025-12-18T20:54:58",
            }
        ):
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert result == []
        assert skipped == 1

    def test_mismatched_timing_lid_falls_back_to_directory_basename(
        self, tmp_path: Path
    ) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        with (
            self._mock_all_parsers(
                parse_e3sm_timing={
                    "execution_id": "different-lid",
                    "run_start_date": "2025-12-18T20:09:33",
                    "run_end_date": "2025-12-18T20:54:58",
                }
            ),
            patch(
                "app.features.ingestion.parsers.parser.logger.warning"
            ) as mock_warning,
        ):
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert skipped == 0
        assert result[0].execution_id == "1.0-0"
        mock_warning.assert_any_call(
            "Timing-file LID '%s' does not match execution directory '%s'. "
            "Using execution directory basename as execution_id.",
            "different-lid",
            "1.0-0",
        )

    def test_mismatched_timing_lid_preserves_distinct_execution_directories(
        self, tmp_path: Path
    ) -> None:
        first_execution_dir = tmp_path / "1.0-0"
        first_execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(first_execution_dir, "001.001")

        second_execution_dir = tmp_path / "1.0-1"
        second_execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(second_execution_dir, "002.002")

        with self._mock_all_parsers(
            parse_e3sm_timing={
                "execution_id": "stale-lid",
                "run_start_date": "2025-12-18T20:09:33",
                "run_end_date": "2025-12-18T20:54:58",
            }
        ):
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert skipped == 0
        assert [parsed.execution_id for parsed in result] == ["1.0-0", "1.0-1"]

    def test_missing_timing_skips_incomplete_run(self, tmp_path: Path) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(
            execution_dir,
            "001.001",
            include_timing=False,
        )

        result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert result == []
        assert skipped == 1

    def test_zip_path_traversal_rejected(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "traversal.zip"
        with zipfile.ZipFile(archive_path, "w") as zip_ref:
            zip_ref.writestr("../evil.txt", "data")

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="escapes extraction directory"):
            parser._extract_zip(str(archive_path), str(extract_dir))

    def test_tar_path_traversal_rejected(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "traversal.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar_ref:
            payload = io.BytesIO(b"data")
            tar_info = tarfile.TarInfo(name="../evil.txt")
            tar_info.size = len(payload.getvalue())
            tar_ref.addfile(tar_info, payload)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="escapes extraction directory"):
            parser._extract_tar_gz(str(archive_path), str(extract_dir))

    def test_tar_symlink_rejected(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "symlink.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar_ref:
            tar_info = tarfile.TarInfo(name="link")
            tar_info.type = tarfile.SYMTYPE
            tar_info.linkname = "target"
            tar_ref.addfile(tar_info)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="Blocked unsafe tar member type"):
            parser._extract_tar_gz(str(archive_path), str(extract_dir))

    def test_main_parser_treats_directory_as_already_extracted(
        self, tmp_path: Path
    ) -> None:
        execution_dir = tmp_path / "1.0-0"
        execution_dir.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir, "001.001")

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert len(result) == 1
        assert skipped == 0

    def test_extract_archive_unsupported_format_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported archive format"):
            parser._extract_archive("/tmp/archive.7z", "/tmp/output")

    def test_incomplete_run_among_valid_runs(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"

        execution_dir_valid = archive_base / "1.0-0"
        execution_dir_valid.mkdir(parents=True)
        self._create_execution_metadata_files(execution_dir_valid, "001.001")

        execution_dir_incomplete = archive_base / "2.0-0"
        execution_dir_incomplete.mkdir(parents=True)
        (execution_dir_incomplete / "dummy.txt").write_text("no required files")

        archive_path = tmp_path / "mixed.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(archive_path, extract_dir)

        assert len(result) == 1
        assert skipped == 1

    def test_multiple_runs_under_same_casename(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        casename_dir = archive_base / "v3.LR.historical_0121"
        casename_dir.mkdir(parents=True)

        run1 = casename_dir / "1081156.251218-200923"
        run1.mkdir()
        self._create_execution_metadata_files(run1, "001.001")

        run2 = casename_dir / "1081290.251218-211543"
        run2.mkdir()
        self._create_execution_metadata_files(run2, "002.002")

        with self._mock_all_parsers():
            result, skipped = parser.main_parser(casename_dir, tmp_path / "out")

        assert len(result) == 2
        assert skipped == 0

    def test_deterministic_sort_order(self, tmp_path: Path) -> None:
        archive_base = tmp_path / "archive_extract"
        casename_dir = archive_base / "case1"
        casename_dir.mkdir(parents=True)

        for name in ["3.0-0", "1.0-0", "2.0-0"]:
            d = casename_dir / name
            d.mkdir()
            self._create_execution_metadata_files(d, "001.001")

        call_order: list[str] = []
        original_locate = parser._locate_metadata_files

        def tracking_locate(execution_dir: str) -> Any:
            call_order.append(os.path.basename(execution_dir))
            return original_locate(execution_dir)

        with (
            self._mock_all_parsers(),
            patch(
                "app.features.ingestion.parsers.parser._locate_metadata_files",
                side_effect=tracking_locate,
            ),
        ):
            parser.main_parser(casename_dir, tmp_path / "out")

        assert call_order == sorted(call_order)
