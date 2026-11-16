import gzip
from pathlib import Path

import pytest

from app.features.ingestion.parsers.git_info import (
    _extract_branch,
    _extract_remote_url,
    parse_git_config,
    parse_git_describe,
    parse_git_log,
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

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (f"{'a' * 40} Merge branch 'x' (PR #1)\n{'b' * 40} Older\n", "a" * 40),
            (f"{'c' * 64} SHA-256 commit\n", "c" * 64),
            ("commit abc1234\n", None),
            (f"{'d' * 41} Too long\n", None),
            ("", None),
        ],
    )
    def test_parse_git_log_first_line_full_hash(
        self, tmp_path: Path, content: str, expected: str | None
    ) -> None:
        file_path = tmp_path / "GIT_LOG.1.0-0.gz"
        with gzip.open(file_path, "wt") as f:
            f.write(content)

        assert parse_git_log(file_path) == {"git_log_commit_hash": expected}

    def test_parse_git_log_uncompressed(self, tmp_path: Path) -> None:
        file_path = tmp_path / "GIT_LOG.1.0-0"
        file_path.write_text(f"{'e' * 40} Subject\n")

        assert parse_git_log(file_path) == {"git_log_commit_hash": "e" * 40}

    def test_parse_git_status_branch(self, tmp_path: Path) -> None:
        content = "On branch feature/59-automate-ingestion\n"
        file_path = tmp_path / "GIT_STATUS"
        file_path.write_text(content)

        result = parse_git_status(str(file_path))

        assert result == {"git_branch": "feature/59-automate-ingestion"}

    def test_extract_branch_returns_none_without_branch_line(self) -> None:
        lines = ["nothing useful here", "HEAD detached at abc123"]

        assert _extract_branch(lines) is None

    def test_parse_git_config_origin_url(self, tmp_path: Path) -> None:
        content = '[remote "origin"]\n    url = https://github.com/example/repo.git\n'
        file_path = tmp_path / "GIT_CONFIG"
        file_path.write_text(content)

        result = parse_git_config(str(file_path))

        assert result == {
            "git_repository_source": "https://github.com/example/repo.git"
        }

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

        assert result == {"git_repository_source": None}

    def test_extract_remote_url_returns_origin_url(self) -> None:
        lines = [
            '[remote "origin"]',
            "fetch = +refs/heads/*:refs/remotes/origin/*",
            "url = https://github.com/example/repo.git",
        ]

        assert _extract_remote_url(lines) == "https://github.com/example/repo.git"

    def test_extract_remote_url_stops_at_next_section(self) -> None:
        lines = [
            '[remote "origin"]',
            "fetch = +refs/heads/*:refs/remotes/origin/*",
            '[branch "main"]',
            "url = https://github.com/example/should-not-be-used.git",
        ]

        assert _extract_remote_url(lines) is None

    def test_extract_remote_url_returns_none_without_origin_section(self) -> None:
        lines = [
            '[remote "upstream"]',
            "url = https://github.com/example/upstream.git",
        ]

        assert _extract_remote_url(lines) is None
