from pathlib import Path
from unittest.mock import patch

from app.features.ingestion.parsers.case_docs import (
    parse_env_build,
    parse_env_case,
    parse_env_run,
)


class TestParseEnvCase:
    def test_extracts_case_root(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASEROOT" value="/tmp/case_root" />
        </config>
        """
        tmp_case = tmp_path / "env_case_caseroot.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["case_root"] == "/tmp/case_root"

    def test_value(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP" value="groupX" />
        </config>
        """
        tmp_case = tmp_path / "env_case.xml"
        tmp_case.write_text(xml_case)
        result = parse_env_case(tmp_case)

        assert result["case_group"] == "groupX"

    def test_text(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP">groupY</entry>
        </config>
        """
        tmp_case = tmp_path / "env_case_text.xml"
        tmp_case.write_text(xml_case)
        result = parse_env_case(tmp_case)

        assert result["case_group"] == "groupY"

    def test_invalid_xml_returns_none(self, tmp_path):
        xml_case = "<config><entry id='CASE_GROUP'>group"
        tmp_case = tmp_path / "env_case_invalid.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["case_group"] is None

    def test_missing_entry_returns_none(self, tmp_path):
        xml_case = """
        <config>
            <entry id="OTHER_GROUP" value="groupZ" />
        </config>
        """
        tmp_case = tmp_path / "env_case_missing.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["case_group"] is None

    def test_campaign_and_experiment_type_are_derived(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE" value="v3.LR.historical_0121" />
        </config>
        """
        tmp_case = tmp_path / "env_case_campaign.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["campaign"] == "v3.LR.historical"
        assert result["experiment_type"] == "historical"

    def test_non_dot_case_name_does_not_set_campaign(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE" value="simple_case_0001" />
        </config>
        """
        tmp_case = tmp_path / "env_case_simple.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["campaign"] is None
        assert result["experiment_type"] is None

    def test_read_error_returns_none(self):
        with patch(
            "app.features.ingestion.parsers.case_docs._open_text",
            side_effect=OSError("boom"),
        ):
            result = parse_env_case(Path("/tmp/missing.xml"))

        assert result["case_name"] is None
        assert result["case_group"] is None


class TestParseEnvBuild:
    def test_value(self, tmp_path):
        xml_build = """
        <config>
            <entry id="COMPILER" value="intel" />
            <entry id="MPILIB" value="mpt" />
        </config>
        """
        tmp_build = tmp_path / "env_build.xml"
        tmp_build.write_text(xml_build)
        result = parse_env_build(tmp_build)

        assert result["compiler"] == "intel"
        assert result["mpilib"] == "mpt"

    def test_text(self, tmp_path):
        xml_build = """
        <config>
            <entry id="COMPILER">gnu</entry>
            <entry id="MPILIB">openmpi</entry>
        </config>
        """
        tmp_build = tmp_path / "env_build_text.xml"
        tmp_build.write_text(xml_build)
        result = parse_env_build(tmp_build)

        assert result["compiler"] == "gnu"
        assert result["mpilib"] == "openmpi"

    def test_missing_entry_returns_none(self, tmp_path):
        xml_build = """
        <config>
            <entry id="COMPILER" value="intel" />
        </config>
        """
        tmp_build = tmp_path / "env_build_missing.xml"
        tmp_build.write_text(xml_build)

        result = parse_env_build(tmp_build)

        assert result["compiler"] == "intel"
        assert result["mpilib"] is None


class TestParseEnvRun:
    def test_extracts_path_artifact_values(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="RUNDIR" value="/tmp/run" />
            <entry id="DOUT_S_ROOT" value="/tmp/archive" />
            <entry id="POSTRUN_SCRIPT">/tmp/post.sh --flag value</entry>
        </config>
        """
        tmp_run = tmp_path / "env_run_paths.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["output_path"] == "/tmp/run"
        assert result["archive_path"] == "/tmp/archive"
        assert result["postprocessing_script"] == "/tmp/post.sh --flag value"

    def test_missing_path_entries_return_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
        </config>
        """
        tmp_run = tmp_path / "env_run_missing_paths.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["output_path"] is None
        assert result["archive_path"] is None
        assert result["postprocessing_script"] is None

    def test_branch_uses_run_refdate(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="branch" />
            <entry id="RUN_STARTDATE" value="2000-01-01" />
            <entry id="RUN_REFDATE" value="1990-01-01" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["initialization_type"] == "branch"
        assert result["simulation_start_date"] == "1990-01-01"
        assert result["simulation_end_date"] is None

    def test_non_branch_uses_run_startdate(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2001-02-03" />
            <entry id="RUN_REFDATE" value="1990-01-01" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_start_date"] == "2001-02-03"

    def test_stop_option_ndays(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="ndays" />
            <entry id="STOP_N" value="10" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] == "2020-01-11"

    def test_stop_option_nmonths(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="nmonths" />
            <entry id="STOP_N" value="2" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] == "2020-03-01"

    def test_stop_option_nyears(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="nyears" />
            <entry id="STOP_N" value="3" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] == "2023-01-01"

    def test_stop_option_date(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="date" />
            <entry id="STOP_DATE" value="20241231" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] == "2024-12-31"

    def test_missing_stop_n_returns_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="ndays" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] is None

    def test_missing_simulation_start_date_returns_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="STOP_OPTION" value="ndays" />
            <entry id="STOP_N" value="10" />
        </config>
        """
        tmp_run = tmp_path / "env_run_missing_start.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_start_date"] is None
        assert result["simulation_end_date"] is None

    def test_missing_stop_date_returns_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="date" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] is None

    def test_invalid_xml_returns_none_dates(self, tmp_path):
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text("<config><entry id='RUN_TYPE'>branch")

        result = parse_env_run(tmp_run)

        assert result["initialization_type"] is None
        assert result["simulation_start_date"] is None
        assert result["simulation_end_date"] is None

    def test_invalid_dates_return_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="invalid-date" />
            <entry id="STOP_OPTION" value="ndays" />
            <entry id="STOP_N" value="2" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_start_date"] == "invalid-date"
        assert result["simulation_end_date"] is None

    def test_unknown_stop_option_returns_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="nhours" />
            <entry id="STOP_N" value="2" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] is None

    def test_invalid_stop_date_returns_none(self, tmp_path):
        xml_run = """
        <config>
            <entry id="RUN_TYPE" value="startup" />
            <entry id="RUN_STARTDATE" value="2020-01-01" />
            <entry id="STOP_OPTION" value="date" />
            <entry id="STOP_DATE" value="invalid" />
        </config>
        """
        tmp_run = tmp_path / "env_run.xml"
        tmp_run.write_text(xml_run)

        result = parse_env_run(tmp_run)

        assert result["simulation_end_date"] is None
