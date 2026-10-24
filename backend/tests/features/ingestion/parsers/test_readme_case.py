import gzip

import pytest

from app.features.ingestion.parsers.readme_case import parse_readme_case


class TestParseReadmeCase:
    @pytest.mark.parametrize("flag", ["--res", "-res"])
    @pytest.mark.parametrize("separator", [" ", "="])
    @pytest.mark.parametrize("compressed", [False, True])
    def test_grid_alias_syntax(self, tmp_path, flag, separator, compressed):
        path = tmp_path / ("README.case.gz" if compressed else "README.case")
        content = f"create_newcase {flag}{separator}'arcticx4v1pg2_ARRM10to60E2r1'\n"
        if compressed:
            with gzip.open(path, "wt") as stream:
                stream.write(content)
        else:
            path.write_text(content)

        result = parse_readme_case(path)

        assert result["grid_alias"] == "arcticx4v1pg2_ARRM10to60E2r1"
        assert "grid_long_name" not in result

    @pytest.mark.parametrize(
        "argument", ["", "-res", "--res", "-res=", "--res=", "-res --compset X"]
    )
    def test_missing_grid_argument(self, tmp_path, argument):
        path = tmp_path / "README.case"
        path.write_text(f"create_newcase {argument}\n")

        assert parse_readme_case(path)["grid_alias"] is None

    @pytest.mark.parametrize("flag", ["-compset", "--compset"])
    @pytest.mark.parametrize("separator", [" ", "="])
    @pytest.mark.parametrize(
        "argument,expected",
        [
            ("WCYCL20TR", "WCYCL20TR"),
            ("F20TR-GHG", "F20TR-GHG"),
            ("MY_ALIAS", "MY_ALIAS"),
            ("1850_EAM_ELM_MPASSI_MPASO_MOSART_SGLC_SWAV", None),
            ("2000_DATM%NYF_DICE%SSMI_DOCN%DOM_DROF%NYF", None),
            ("atm:DATM%NYF_rof:DROF%NYF_scn:2000", None),
        ],
    )
    def test_component_set_syntax(self, tmp_path, flag, separator, argument, expected):
        path = tmp_path / "README.case"
        path.write_text(f"create_newcase {flag}{separator}'{argument}' --res ne30\n")

        result = parse_readme_case(path)

        assert result["compset_alias"] == expected
        assert "compset_long_name" not in result
        assert result["grid_alias"] == "ne30"

    @pytest.mark.parametrize(
        "argument", ["", "--compset", "--compset=", "--compset --res ne30"]
    )
    def test_missing_component_argument(self, tmp_path, argument):
        path = tmp_path / "README.case"
        path.write_text(f"create_newcase {argument}\n")

        assert parse_readme_case(path)["compset_alias"] is None

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
        assert result["grid_alias"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset_alias"] == "WCYCL20TR"

    def test_parse_gz(self, sample_gz_readme_case):
        result = parse_readme_case(sample_gz_readme_case)

        assert result["creation_date"] == "2025-12-18 22:36:01"
        assert result["grid_alias"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset_alias"] == "WCYCL20TR"

    def test_missing_fields(self, tmp_path):
        content = (
            "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121\n"
        )
        file_path = tmp_path / "README.case"
        file_path.write_text(content)
        result = parse_readme_case(file_path)

        assert result["creation_date"] == "2025-12-18 22:36:01"
        assert result["grid_alias"] is None
        assert result["compset_alias"] is None

    def test_missing_timestamp_returns_none(self, tmp_path):
        content = "/path/create_newcase --case v3.LR.historical_0121 --res ne30 --compset WCYCL20TR\n"
        file_path = tmp_path / "README.case"
        file_path.write_text(content)

        result = parse_readme_case(file_path)

        assert result["creation_date"] is None
        assert result["grid_alias"] == "ne30"
        assert result["compset_alias"] == "WCYCL20TR"

    def test_parse_flag_equals_format(self, tmp_path):
        content = (
            "2025-12-18 22:36:01: /path/create_newcase --case v3.LR.historical_0121 "
            "--res=ne30pg2_r05_IcoswISC30E3r5 --compset=WCYCL20TR\n"
        )
        file_path = tmp_path / "README.case"
        file_path.write_text(content)
        result = parse_readme_case(file_path)

        assert result["grid_alias"] == "ne30pg2_r05_IcoswISC30E3r5"
        assert result["compset_alias"] == "WCYCL20TR"
