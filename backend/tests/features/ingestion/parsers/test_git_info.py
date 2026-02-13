from pathlib import Path

from app.features.ingestion.parsers.git_info import (
    parse_git_config,
    parse_git_describe,
    parse_git_status,
)


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

    def test_parse_git_describe_fallback_tag_and_hash(self, tmp_path: Path) -> None:
        content = "release-2024-gabcdef1\n"
        file_path = tmp_path / "GIT_DESCRIBE"
        file_path.write_text(content)

        result = parse_git_describe(str(file_path))

        assert result["git_tag"] == "release"
        assert result["git_commit_hash"] == "abcdef1"

    def test_parse_git_status_branch(self, tmp_path: Path) -> None:
        content = "On branch feature/59-automate-ingestion\n"
        file_path = tmp_path / "GIT_STATUS"
        file_path.write_text(content)

        result = parse_git_status(str(file_path))

        assert result == "feature/59-automate-ingestion"

    def test_parse_git_config_origin_url(self, tmp_path: Path) -> None:
        content = '[remote "origin"]\n    url = https://github.com/example/repo.git\n'
        file_path = tmp_path / "GIT_CONFIG"
        file_path.write_text(content)

        result = parse_git_config(str(file_path))

        assert result == "https://github.com/example/repo.git"

    def test_parse_git_config_missing_origin_url(self, tmp_path: Path) -> None:
        content = (
            '[remote "origin"]\n'
            "    fetch = +refs/heads/*:refs/remotes/origin/*\n"
            '[branch "main"]\n'
            "    remote = origin\n"
        )
        file_path = tmp_path / "GIT_CONFIG"
        file_path.write_text(content)

        result = parse_git_config(str(file_path))

        assert result is None
