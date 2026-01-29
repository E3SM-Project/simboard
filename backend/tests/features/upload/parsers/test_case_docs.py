from app.features.upload.parsers.case_docs import parse_env_files
import gzip


class TestCaseDocsParser:
    def test_parse_env_files_all_attributes(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP" value="group1" />
        </config>
        """
        xml_build = """
        <config>
            <entry id="COMPILER" value="intel" />
            <entry id="MPILIB" value="mpt" />
        </config>
        """
        tmp_case = tmp_path / "env_case.xml"
        tmp_build = tmp_path / "env_build.xml"
        tmp_case.write_text(xml_case)
        tmp_build.write_text(xml_build)

        result = parse_env_files(tmp_case, tmp_build)

        assert result["case_group"] == "group1"
        assert result["compiler"] == "intel"
        assert result["mpilib"] == "mpt"

    def test_parse_env_files_text_content(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP">group2</entry>
        </config>
        """
        xml_build = """
        <config>
            <entry id="COMPILER">gnu</entry>
            <entry id="MPILIB">openmpi</entry>
        </config>
        """
        tmp_case = tmp_path / "env_case_text.xml"
        tmp_build = tmp_path / "env_build_text.xml"
        tmp_case.write_text(xml_case)
        tmp_build.write_text(xml_build)

        result = parse_env_files(tmp_case, tmp_build)

        assert result["case_group"] == "group2"
        assert result["compiler"] == "gnu"
        assert result["mpilib"] == "openmpi"

    def test_parse_env_files_mixed(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP" value="group3" />
        </config>
        """
        xml_build = """
        <config>
            <entry id="COMPILER">gnu</entry>
            <entry id="MPILIB" value="mpt" />
        </config>
        """
        tmp_case = tmp_path / "env_case_mixed.xml"
        tmp_build = tmp_path / "env_build_mixed.xml"
        tmp_case.write_text(xml_case)
        tmp_build.write_text(xml_build)

        result = parse_env_files(tmp_case, tmp_build)

        assert result["case_group"] == "group3"
        assert result["compiler"] == "gnu"
        assert result["mpilib"] == "mpt"

    def test_parse_env_files_gz(self, tmp_path):

        xml_case = """
        <config>
            <entry id="CASE_GROUP">gz_group</entry>
        </config>
        """
        xml_build = """
        <config>
            <entry id="COMPILER" value="gnu" />
            <entry id="MPILIB">openmpi</entry>
        </config>
        """
        tmp_case = tmp_path / "env_case.xml.gz"
        tmp_build = tmp_path / "env_build.xml.gz"
        with gzip.open(tmp_case, "wt") as f:
            f.write(xml_case)
        with gzip.open(tmp_build, "wt") as f:
            f.write(xml_build)

        result = parse_env_files(tmp_case, tmp_build)

        assert result["case_group"] == "gz_group"
        assert result["compiler"] == "gnu"
        assert result["mpilib"] == "openmpi"

    def test_parse_env_files_missing(self, tmp_path):
        xml_case = """
        <config>
        </config>
        """
        xml_build = """
        <config>
            <entry id="COMPILER" value="gnu" />
        </config>
        """
        tmp_case = tmp_path / "env_case_empty.xml"
        tmp_build = tmp_path / "env_build_missing.xml"
        tmp_case.write_text(xml_case)
        tmp_build.write_text(xml_build)

        result = parse_env_files(tmp_case, tmp_build)

        assert result["case_group"] is None
        assert result["compiler"] == "gnu"
        assert result["mpilib"] is None
