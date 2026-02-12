import gzip

import pytest

from app.features.upload.parsers.readme_case import parse_readme_case


class TestParseReadmeCase:
    @pytest.fixture
    def sample_readme_case(self, tmp_path):
        content = (
            "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121 --res ne30pg2_r05_IcoswISC30E3r5 --compset WCYCL20TR\n"
            "2025-12-18 22:36:01: Compset longname is ...\n"
        )
        file_path = tmp_path / "README.case"
        file_path.write_text(content)
        
        return file_path

    @pytest.fixture
    def sample_gz_readme_case(self, tmp_path):
        content = "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121 --res ne30pg2_r05_IcoswISC30E3r5 --compset WCYCL20TR\n"
        file_path = tmp_path / "README.case.gz"

        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write(content)

        return file_path

    def test_parse_plain(self, sample_readme_case):
        result = parse_readme_case(sample_readme_case)

        assert result["creation_date"] == "2025-12-18 22:36:01"
        assert result["grid_name"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset"] == "WCYCL20TR"

    def test_parse_gz(self, sample_gz_readme_case):
        result = parse_readme_case(sample_gz_readme_case)

        assert result["creation_date"] == "2025-12-18 22:36:01"
        assert result["grid_name"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset"] == "WCYCL20TR"

    def test_missing_fields(self, tmp_path):
        content = (
            "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121\n"
        )
        file_path = tmp_path / "README.case"
        file_path.write_text(content)
        result = parse_readme_case(file_path)

        assert result["creation_date"] == "2025-12-18 22:36:01"
        assert result["grid_name"] is None
        assert result["compset"] is None

    def test_parse_flag_equals_format(self, tmp_path):
        content = (
            "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121 "
            "--res=ne30pg2_r05_IcoswISC30E3r5 --compset=WCYCL20TR\n"
        )
        file_path = tmp_path / "README.case"
        file_path.write_text(content)
        result = parse_readme_case(file_path)

        assert result["grid_name"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset"] == "WCYCL20TR"
