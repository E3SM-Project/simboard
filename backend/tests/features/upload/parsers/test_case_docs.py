from app.features.upload.parsers.case_docs import parse_env_build, parse_env_case


class TestParseEnvCase:
    def test_value(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP" value="groupX" />
        </config>
        """
        tmp_case = tmp_path / "env_case.xml"
        tmp_case.write_text(xml_case)
        result = parse_env_case(tmp_case)
        assert result["group_name"] == "groupX"

    def test_text(self, tmp_path):
        xml_case = """
        <config>
            <entry id="CASE_GROUP">groupY</entry>
        </config>
        """
        tmp_case = tmp_path / "env_case_text.xml"
        tmp_case.write_text(xml_case)
        result = parse_env_case(tmp_case)
        assert result["group_name"] == "groupY"

    def test_invalid_xml_returns_none(self, tmp_path):
        xml_case = "<config><entry id='CASE_GROUP'>group"
        tmp_case = tmp_path / "env_case_invalid.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["group_name"] is None

    def test_missing_entry_returns_none(self, tmp_path):
        xml_case = """
        <config>
            <entry id="OTHER_GROUP" value="groupZ" />
        </config>
        """
        tmp_case = tmp_path / "env_case_missing.xml"
        tmp_case.write_text(xml_case)

        result = parse_env_case(tmp_case)

        assert result["group_name"] is None


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
