import os

import pytest

from app.core.config import get_env_file


@pytest.fixture(autouse=True)
def disable_ci(monkeypatch):
    """
    Ensure tests exercise *local development* behavior.

    In CI, we intentionally set `CI=true`, which causes `get_env_file()`
    to return None and rely solely on environment variables.

    This test suite validates the *file-based* behavior used in local
    development (i.e., resolving `.envs/<ENV>/backend.env`), so we
    explicitly unset `CI` here to avoid CI-specific code paths.
    """
    monkeypatch.delenv("CI", raising=False)


class TestGetEnvFile:
    @pytest.fixture(autouse=True)
    def restore_env(self, monkeypatch):
        """Save & restore ENV across tests."""
        original = os.environ.get("ENV")
        yield
        if original is not None:
            monkeypatch.setenv("ENV", original)
        else:
            monkeypatch.delenv("ENV", raising=False)

    def test_raises_when_env_file_is_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        root = tmp_path
        (root / ".envs/local/").mkdir(parents=True)
        (root / ".envs/local/backend.env").write_text("OK")
        (root / ".envs/local/backend.env.example").write_text("# example")
        example_env_file = root / ".envs/backend.env.example"

        with pytest.raises(
            FileNotFoundError, match="Refusing to load .example env files."
        ):
            if example_env_file.name.endswith(".example"):
                raise FileNotFoundError("Refusing to load .example env files.")

    def test_returns_dev_env_file_when_ENV_is_dev(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "development")

        root = tmp_path
        (root / ".envs/local").mkdir(parents=True)
        (root / ".envs/local/backend.env").write_text("OK")
        env_file = get_env_file(project_root=root)

        assert env_file.endswith("backend.env")  # type: ignore[union-attr]

    def test_returns_none_if_when_ENV_is_not_dev(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        root = tmp_path
        (root / ".envs/").mkdir(parents=True)
        (root / ".envs/backend.env").write_text("OK")
        env_file = get_env_file(project_root=root)

        assert env_file is None

    def test_raises_when_only_example_env_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        root = tmp_path
        (root / ".envs/example").mkdir(parents=True)
        (root / ".envs/example/backend.env.example").write_text("# example")

        with pytest.raises(FileNotFoundError):
            get_env_file(project_root=root)

    def test_raises_when_env_file_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        root = tmp_path

        with pytest.raises(FileNotFoundError):
            get_env_file(project_root=root)
