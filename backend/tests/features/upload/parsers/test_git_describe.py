from pathlib import Path

from app.features.upload.parsers.git_describe import parse_git_describe_file

TEST_DIR = Path(__file__).parent


class TestGitDescribeParser:
    def test_parse_git_describe_basic(self):
        # Simulate a typical git describe string
        content = "v2.0.0-beta.3-3091-g3219b44fc\n"
        tmp = TEST_DIR / "GIT_DESCRIBE"
        tmp.write_text(content)
        result = parse_git_describe_file(tmp)

        assert result["version"] == "v2.0.0-beta.3-3091-g3219b44fc"
        assert result["git_tag"] == "v2.0.0-beta.3-3091"
        assert result["git_commit_hash"] == "3219b44fc"

        tmp.unlink()

    def test_parse_git_describe_no_commit(self):
        # No commit hash, just a tag
        content = "v2.0.0\n"

        tmp = TEST_DIR / "GIT_DESCRIBE"
        tmp.write_text(content)
        result = parse_git_describe_file(tmp)

        assert result["version"] == "v2.0.0"
        assert result["git_tag"] is None
        assert result["git_commit_hash"] is None

        tmp.unlink()

    def test_parse_git_describe_empty(self):
        content = "\n\n"
        tmp = TEST_DIR / "GIT_DESCRIBE"
        tmp.write_text(content)
        result = parse_git_describe_file(tmp)

        assert result["version"] is None
        assert result["git_tag"] is None
        assert result["git_commit_hash"] is None

        tmp.unlink()
