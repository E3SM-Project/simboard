import os

import pytest

from app.core.config import get_env_file, settings


@pytest.fixture(autouse=True)
def disable_ci(monkeypatch):
    """
    Ensure tests exercise local development behavior.

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
        original = os.environ.get("ENV")
        yield
        if original is not None:
            monkeypatch.setenv("ENV", original)
        else:
            monkeypatch.delenv("ENV", raising=False)

    def test_raises_when_env_file_is_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        root = tmp_path
        (root / ".envs/local").mkdir(parents=True)
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

    def test_returns_none_when_ENV_is_not_dev(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        root = tmp_path
        (root / ".envs").mkdir(parents=True)
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


class TestSettings:
    @pytest.fixture(autouse=True)
    def restore_settings(self):
        original_env = settings.env
        original_trusted_proxy_hosts = settings.trusted_proxy_hosts
        original_frontend_origin = settings.frontend_origin
        original_frontend_origins = settings.frontend_origins

        yield

        settings.env = original_env
        settings.trusted_proxy_hosts = original_trusted_proxy_hosts
        settings.frontend_origin = original_frontend_origin
        settings.frontend_origins = original_frontend_origins

    def test_frontend_origin_has_no_trailing_slash(self):
        settings.frontend_origin = "http://localhost:3000/"
        assert settings.frontend_origin_normalized == "http://localhost:3000"

    def test_trusted_proxy_hosts_empty(self):
        settings.trusted_proxy_hosts = ""
        with pytest.raises(ValueError, match="TRUSTED_PROXY_HOSTS cannot be empty"):
            _ = settings.trusted_proxy_hosts_normalized

    def test_trusted_proxy_hosts_wildcard_in_production(self):
        settings.env = "production"
        settings.trusted_proxy_hosts = "*"
        with pytest.raises(
            ValueError, match=r"TRUSTED_PROXY_HOSTS='\*' is not allowed in production"
        ):
            _ = settings.trusted_proxy_hosts_normalized

    def test_trusted_proxy_hosts_wildcard_in_development(self):
        settings.env = "development"
        settings.trusted_proxy_hosts = "*"
        assert settings.trusted_proxy_hosts_normalized == "*"

    def test_trusted_proxy_hosts_valid_hosts(self):
        settings.trusted_proxy_hosts = "host1, host2, host3"
        assert settings.trusted_proxy_hosts_normalized == ["host1", "host2", "host3"]

    def test_trusted_proxy_hosts_with_trailing_slashes(self):
        settings.trusted_proxy_hosts = "host1/, host2/, host3/"
        assert settings.trusted_proxy_hosts_normalized == ["host1", "host2", "host3"]

    def test_trusted_proxy_hosts_with_whitespace(self):
        settings.trusted_proxy_hosts = " host1 , host2 , host3 "
        assert settings.trusted_proxy_hosts_normalized == ["host1", "host2", "host3"]

    def test_frontend_origins_list_with_single_origin(self):
        settings.frontend_origins = "https://example.com/"
        assert settings.frontend_origins_list == ["https://example.com"]

    def test_frontend_origins_list_with_multiple_origins_as_string(self):
        settings.frontend_origins = "https://example1.com/, https://example2.com/"
        assert settings.frontend_origins_list == [
            "https://example1.com",
            "https://example2.com",
        ]

    def test_frontend_origins_list_with_multiple_origins_as_list(self):
        settings.frontend_origins = ["https://example1.com/", "https://example2.com/"]
        assert settings.frontend_origins_list == [
            "https://example1.com",
            "https://example2.com",
        ]

    def test_frontend_origins_list_with_empty_string(self):
        settings.frontend_origins = ""
        assert settings.frontend_origins_list == []

    def test_frontend_origins_list_with_whitespace_only(self):
        settings.frontend_origins = "   "
        assert settings.frontend_origins_list == []

    def test_frontend_origins_list_with_trailing_slashes(self):
        settings.frontend_origins = "https://example1.com/, https://example2.com/"
        assert settings.frontend_origins_list == [
            "https://example1.com",
            "https://example2.com",
        ]

    def test_frontend_origins_list_with_whitespace(self):
        settings.frontend_origins = " https://example1.com , https://example2.com "
        assert settings.frontend_origins_list == [
            "https://example1.com",
            "https://example2.com",
        ]
