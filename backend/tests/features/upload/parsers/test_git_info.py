from pathlib import Path

from app.features.upload.parsers.git_info import parse_git_describe


class TestGitInfoParser:
    def test_parse_git_describe_with_prerelease_and_commits(
        self, tmp_path: Path
    ) -> None:
        content = "v2.0.0-beta.3-3091-g3219b44fc\n"
        file_path = tmp_path / "GIT_DESCRIBE"
        file_path.write_text(content)

        result = parse_git_describe(str(file_path))

        assert result["git_tag"] == "v2.0.0-beta.3-3091"
        assert result["git_commit_hash"] == "3219b44fc"
