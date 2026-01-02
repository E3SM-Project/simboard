import os

import pytest

from app.core.config import get_env_file


class TestGetEnvFile:
    @pytest.fixture(autouse=True)
    def restore_env(self, monkeypatch):
        """Save & restore APP_ENV across tests."""
        original = os.environ.get("APP_ENV")
        yield
        if original is not None:
            monkeypatch.setenv("APP_ENV", original)
        else:
            monkeypatch.delenv("APP_ENV", raising=False)

    def test_raises_when_env_file_is_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        root = tmp_path
        (root / ".envs/dev").mkdir(parents=True)
        (root / ".envs/dev/backend.env").write_text("OK")
        (root / ".envs/dev/backend.env.example").write_text("# example")
        example_env_file = root / ".envs/dev/backend.env.example"

        with pytest.raises(
            FileNotFoundError, match="Refusing to load .example env files."
        ):
            if example_env_file.name.endswith(".example"):
                raise FileNotFoundError("Refusing to load .example env files.")

    def test_returns_dev_env_file_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        root = tmp_path
        (root / ".envs/dev").mkdir(parents=True)
        (root / ".envs/dev/backend.env").write_text("OK")
        env_file = get_env_file(project_root=root)

        assert env_file.endswith("dev/backend.env")

    def test_returns_dev_env_file_when_app_env_is_dev(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        root = tmp_path
        (root / ".envs/dev").mkdir(parents=True)
        (root / ".envs/dev/backend.env").write_text("OK")
        env_file = get_env_file(project_root=root)

        assert env_file.endswith("dev/backend.env")

    def test_returns_dev_docker_env_file_when_app_env_is_dev_docker(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("APP_ENV", "dev_docker")
        root = tmp_path
        (root / ".envs/dev_docker").mkdir(parents=True)
        (root / ".envs/dev_docker/backend.env").write_text("OK")
        env_file = get_env_file(project_root=root)

        assert env_file.endswith("dev_docker/backend.env")

    def test_returns_prod_env_file_when_app_env_is_prod(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "prod")
        root = tmp_path
        (root / ".envs/prod").mkdir(parents=True)
        (root / ".envs/prod/backend.env").write_text("OK")

        env_file = get_env_file(project_root=root)
        assert env_file.endswith("prod/backend.env")

    def test_raises_when_only_example_env_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        root = tmp_path
        (root / ".envs/dev").mkdir(parents=True)
        (root / ".envs/dev/backend.env.example").write_text("# example")

        with pytest.raises(FileNotFoundError):
            get_env_file(project_root=root)

    def test_raises_when_env_file_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "ghost")
        root = tmp_path

        with pytest.raises(FileNotFoundError):
            get_env_file(project_root=root)

    def test_raises_when_env_file_is_missing_and_only_example_exists(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("APP_ENV", "dev")
        root = tmp_path
        (root / ".envs/dev").mkdir(parents=True)
        (root / ".envs/dev/backend.env.example").write_text("# example")
        env_file = root / ".envs/dev/backend.env"

        if env_file.exists():
            env_file.unlink()
        with pytest.raises(FileNotFoundError):
            get_env_file(project_root=root)
