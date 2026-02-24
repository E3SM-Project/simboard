"""Integration tests for the parser module focusing on public API."""

import gzip
import io
import os
import tarfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest

from app.features.ingestion.parsers import parser


class TestMainParser:
    @staticmethod
    def _create_experiment_files(exp_dir: Path, version: str) -> None:
        """Create standard experiment files for testing.

        Parameters
        ----------
        exp_dir : Path
            Directory where experiment files will be created.
        version : str
            Version string for file naming (e.g., "001.001").
        """
        # Create required e3sm_timing file
        timing_file = exp_dir / f"e3sm_timing.{version}"
        timing_file.write_text("timing data")

        # Create required CaseStatus file
        with gzip.open(exp_dir / f"CaseStatus.{version.split('.')[0]}.gz", "wt") as f:
            f.write("case status")

        # Create required CaseDocs/README
        casedocs = exp_dir / "CaseDocs"
        casedocs.mkdir(exist_ok=True)
        with gzip.open(casedocs / f"README.case.{version.split('.')[0]}.gz", "wt") as f:
            f.write("readme content")

        # Create required GIT_DESCRIBE file
        with gzip.open(exp_dir / f"GIT_DESCRIBE.{version.split('.')[0]}.gz", "wt") as f:
            f.write("describe content")

    @staticmethod
    def _create_optional_files(exp_dir: Path, version: str) -> None:
        """Create optional git configuration files for testing.

        Parameters
        ----------
        exp_dir : Path
            Directory where git files will be created.
        version : str
            Version string for file naming (e.g., "001").
        """
        version_base = version.split(".")[0] if "." in version else version

        with gzip.open(exp_dir / f"GIT_CONFIG.{version_base}.gz", "wt") as f:
            f.write("https://github.com/test/repo")
        with gzip.open(exp_dir / f"GIT_STATUS.{version_base}.gz", "wt") as f:
            f.write("main")

    @staticmethod
    def _create_zip_archive(base_dir: Path, archive_path: Path) -> None:
        """Create a ZIP archive from directory contents.

        Parameters
        ----------
        base_dir : Path
            Directory relative to which paths are calculated.
        archive_path : Path
            Path where ZIP archive will be created.
        """
        zip_file = zipfile.ZipFile(archive_path, "w")

        for root, _dirs, files_list in os.walk(str(base_dir)):
            for file in files_list:
                file_path = Path(root) / file
                arcname = str(file_path.relative_to(str(base_dir)))

                zip_file.write(file_path, arcname)

        zip_file.close()

    @staticmethod
    def _create_tar_gz_archive(base_dir: Path, archive_path: Path) -> None:
        """Create a TAR.GZ archive from directory contents.

        Parameters
        ----------
        base_dir : Path
            Directory relative to which paths are calculated.
        archive_path : Path
            Path where TAR.GZ archive will be created.
        """
        tar_file = tarfile.open(archive_path, "w:gz")

        for root, _dirs, files_list in os.walk(str(base_dir)):
            for file in files_list:
                file_path = Path(root) / file
                arcname = str(file_path.relative_to(str(base_dir)))

                tar_file.add(file_path, arcname=arcname)

        tar_file.close()

    @contextmanager
    def _mock_all_parsers(self, **kwargs: Any) -> Generator[None, None, None]:
        """Context manager to mock all parser functions with sensible defaults.

        Parameters
        ----------
        **kwargs : dict
            Override default return values for specific parsers:
            parse_e3sm_timing, parse_readme_case, parse_case_status,
            parse_git_describe, parse_git_config, parse_git_status.

        Yields
        ------
        None
            Context manager available for use in with statement.
        """
        # Set up default return values
        defaults = {
            "parse_e3sm_timing": {
                "case_name": "test_case",
                "campaign": "test",
                "machine": "test",
            },
            "parse_readme_case": {},
            "parse_case_status": {},
            "parse_git_describe": {},
            "parse_git_config": None,
            "parse_git_status": None,
        }
        defaults.update(kwargs)

        with (
            patch("app.features.ingestion.parsers.parser.parse_e3sm_timing") as m1,
            patch("app.features.ingestion.parsers.parser.parse_readme_case") as m2,
            patch("app.features.ingestion.parsers.parser.parse_case_status") as m3,
            patch("app.features.ingestion.parsers.parser.parse_git_describe") as m4,
            patch("app.features.ingestion.parsers.parser.parse_git_config") as m5,
            patch("app.features.ingestion.parsers.parser.parse_git_status") as m6,
        ):
            m1.return_value = defaults["parse_e3sm_timing"]
            m2.return_value = defaults["parse_readme_case"]
            m3.return_value = defaults["parse_case_status"]
            m4.return_value = defaults["parse_git_describe"]
            m5.return_value = defaults["parse_git_config"]
            m6.return_value = defaults["parse_git_status"]
            yield

    def test_with_valid_zip_archive(self, tmp_path: Path) -> None:
        """Test processing a valid ZIP archive with experiments."""
        # Create experiment directory structure
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "1.0-0"
        exp_dir.mkdir(parents=True)

        # Create standard required files
        self._create_experiment_files(exp_dir, "001.001")

        # Create ZIP archive
        archive_path = tmp_path / "archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Mock parser functions and verify experiment was found and parsed
        with self._mock_all_parsers():
            result = parser.main_parser(archive_path, extract_dir)
            assert len(result) > 0
            assert any("1.0-0" in key for key in result.keys())

    def test_with_tar_gz_archive(self, tmp_path: Path) -> None:
        """Test processing a TAR.GZ archive."""
        # Create experiment directory
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "2.5-10"
        exp_dir.mkdir(parents=True)

        # Create standard required files
        self._create_experiment_files(exp_dir, "002.002")

        # Create TAR.GZ archive
        archive_path = tmp_path / "archive.tar.gz"
        self._create_tar_gz_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Mock parser functions and verify experiment was found and parsed
        with self._mock_all_parsers(parse_e3sm_timing={"case_name": "tar_test"}):
            result = parser.main_parser(archive_path, extract_dir)
            assert len(result) > 0
            assert any("2.5-10" in key for key in result.keys())

    def test_with_multiple_experiments(self, tmp_path: Path) -> None:
        """Test processing archive with multiple experiments."""
        archive_base = tmp_path / "archive_extract"
        archive_base.mkdir()

        # Create first experiment
        exp_dir1 = archive_base / "1.0-0"
        exp_dir1.mkdir(parents=True)
        self._create_experiment_files(exp_dir1, "001.001")

        # Create second experiment
        exp_dir2 = archive_base / "2.0-0"
        exp_dir2.mkdir(parents=True)
        self._create_experiment_files(exp_dir2, "002.002")

        # Create ZIP archive
        archive_path = tmp_path / "multi_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Mock parser functions and verify both experiments were found
        with self._mock_all_parsers(parse_e3sm_timing={"case_name": "test"}):
            result = parser.main_parser(archive_path, extract_dir)
            assert len(result) == 2
            assert any("1.0-0" in key for key in result.keys())
            assert any("2.0-0" in key for key in result.keys())

    def test_with_nested_experiments(self, tmp_path: Path) -> None:
        """Test finding experiments in nested directories.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory provided by pytest.
        """
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "parent" / "1.0-0"
        exp_dir.mkdir(parents=True)

        # Create standard required files
        self._create_experiment_files(exp_dir, "001.001")

        # Create ZIP archive
        archive_path = tmp_path / "nested_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Mock parser functions and verify nested experiment was found
        with self._mock_all_parsers(parse_e3sm_timing={"case_name": "nested_test"}):
            result = parser.main_parser(archive_path, extract_dir)
            assert len(result) > 0
            assert any("1.0-0" in key for key in result.keys())

    def test_missing_required_files_skips_incomplete_run(self, tmp_path: Path) -> None:
        """Test that incomplete runs (missing required files) are skipped."""
        # Create experiment directory WITHOUT required files
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "1.0-0"
        exp_dir.mkdir(parents=True)
        (exp_dir / "dummy.txt").write_text("dummy")

        # Create ZIP archive
        archive_path = tmp_path / "bad_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Incomplete runs are skipped; result is empty rather than an error
        result = parser.main_parser(archive_path, extract_dir)
        assert result == {}

    def test_multiple_matching_files_raises_error(self, tmp_path: Path) -> None:
        """Test error when multiple files match a pattern."""
        # Create experiment with duplicate files
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "1.0-0"
        exp_dir.mkdir(parents=True)

        # Create duplicate e3sm_timing files (violates single-file requirement)
        (exp_dir / "e3sm_timing.001.001").write_text("timing1")
        (exp_dir / "e3sm_timing.002.002").write_text("timing2")

        # Create other required files
        with gzip.open(exp_dir / "CaseStatus.001.gz", "wt") as f:
            f.write("status")
        casedocs = exp_dir / "CaseDocs"
        casedocs.mkdir()
        with gzip.open(casedocs / "README.case.001.gz", "wt") as f:
            f.write("readme")
        with gzip.open(exp_dir / "GIT_DESCRIBE.001.gz", "wt") as f:
            f.write("describe")

        # Create ZIP archive
        archive_path = tmp_path / "duplicate_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Should raise ValueError for multiple matching files
        with pytest.raises(ValueError, match="Multiple files matching pattern"):
            parser.main_parser(archive_path, extract_dir)

    def test_unsupported_archive_format_raises_error(self, tmp_path: Path) -> None:
        """Test error for unsupported archive formats."""
        archive_path = tmp_path / "archive.rar"
        archive_path.write_text("not a real archive")

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="Unsupported archive format"):
            parser.main_parser(str(archive_path), extract_dir)

    def test_no_experiment_directories_raises_error(self, tmp_path: Path) -> None:
        """Test error when no experiment directories are found.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory provided by pytest.

        Raises
        ------
        FileNotFoundError
            Expected when no valid experiment directories are discovered.
        """
        # Create a ZIP archive with no experiment directories
        archive_base = tmp_path / "archive_extract"
        archive_base.mkdir()
        (archive_base / "some_other_dir").mkdir()
        (archive_base / "some_other_dir" / "file.txt").write_text("data")

        # Create ZIP archive
        archive_path = tmp_path / "empty_archive.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Should raise FileNotFoundError when no experiments found
        with pytest.raises(FileNotFoundError, match="No experiment directories found"):
            parser.main_parser(archive_path, extract_dir)

    def test_with_optional_files(self, tmp_path):
        """Test handling optional files properly."""
        # Create experiment with optional files
        archive_base = tmp_path / "archive_extract"
        exp_dir = archive_base / "1.0-0"
        exp_dir.mkdir(parents=True)

        # Create required files
        self._create_experiment_files(exp_dir, "001.001")

        # Create optional git files
        self._create_optional_files(exp_dir, "001")

        # Create ZIP archive
        archive_path = tmp_path / "with_optional.zip"
        self._create_zip_archive(archive_base, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        # Mock parsers with optional file returns
        with self._mock_all_parsers(
            parse_git_config="https://github.com/test/repo", parse_git_status="main"
        ):
            result = parser.main_parser(archive_path, extract_dir)
            assert len(result) > 0

    def test_zip_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Test that ZIP extraction rejects path traversal entries."""
        archive_path = tmp_path / "traversal.zip"
        with zipfile.ZipFile(archive_path, "w") as zip_ref:
            zip_ref.writestr("../evil.txt", "data")

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="escapes extraction directory"):
            parser._extract_zip(str(archive_path), str(extract_dir))

    def test_tar_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Test that TAR.GZ extraction rejects path traversal entries."""
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
        """Test that TAR.GZ extraction rejects symlink entries."""
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
        """Test non-archive directory input path branch in main_parser."""
        exp_dir = tmp_path / "1.0-0"
        exp_dir.mkdir(parents=True)
        self._create_experiment_files(exp_dir, "001.001")

        with self._mock_all_parsers():
            result = parser.main_parser(tmp_path, tmp_path / "unused_output")

        assert len(result) == 1
        assert any("1.0-0" in key for key in result)

    def test_extract_archive_unsupported_format_raises_error(self) -> None:
        """Test _extract_archive direct unsupported-extension branch."""
        with pytest.raises(ValueError, match="Unsupported archive format"):
            parser._extract_archive("/tmp/archive.7z", "/tmp/output")

    def test_parse_experiment_files_supports_single_value_spec(self) -> None:
        """Test single_value parser path in _parse_experiment_files."""
        original_specs = parser.FILE_SPECS.copy()
        try:
            parser.FILE_SPECS["single_value_test"] = {
                "pattern": r"dummy",
                "location": "root",
                "parser": lambda _path: "single-output",
                "required": False,
                "single_value": "campaign",
            }
            files: dict[str, str | None] = {key: None for key in parser.FILE_SPECS}
            files["single_value_test"] = "/tmp/dummy"

            result = parser._parse_experiment_files(files)

            assert result["campaign"] == "single-output"
        finally:
            parser.FILE_SPECS.clear()
            parser.FILE_SPECS.update(original_specs)
