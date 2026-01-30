import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file(project_root: Path | None = None) -> str | None:
    """
    Determine which .env file to load based on ENV.

    - ENV=development → load .envs/local/backend.env
    - ENV=production  → rely on process environment only
    - ENV=test        → rely on test harness
    """
    env = os.getenv("ENV", "development")

    if env != "development":
        return None

    if project_root is None:  # pragma: no cover
        project_root = Path(__file__).resolve().parents[3]

    env_file = project_root / ".envs" / "local" / "backend.env"

    if not env_file.exists():
        raise FileNotFoundError(
            f"Missing development env file: {env_file}\n"
            "Create it or set ENV=production to rely on environment variables."
        )

    return str(env_file)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General application configuration
    # ----------------------------------------
    env: str = "development"
    port: int = 8000

    # Network Configuration
    # ----------------------------------------
    trusted_proxy_hosts: str

    @property
    def trusted_proxy_hosts_normalized(self) -> str | list[str]:
        value = self.trusted_proxy_hosts.strip()

        if not value:
            raise ValueError("TRUSTED_PROXY_HOSTS cannot be empty")

        if value == "*":
            if self.env == "production":
                raise ValueError("TRUSTED_PROXY_HOSTS='*' is not allowed in production")
            return "*"

        hosts = [h.strip() for h in value.split(",") if h.strip()]

        if not hosts:
            raise ValueError("TRUSTED_PROXY_HOSTS must contain at least one host")

        return hosts

    # Frontend
    # ----------------------------------------
    # Primary frontend (used for redirects, links, emails, etc.)
    frontend_origin: str = Field(
        validation_alias="FRONTEND_ORIGIN",
        description="Primary frontend origin (staging or production)",
    )

    frontend_auth_redirect_url: str = Field(
        validation_alias="FRONTEND_AUTH_REDIRECT_URL",
        description="OAuth redirect URL on the primary frontend",
    )

    # All frontends allowed to call the API (CORS)
    frontend_origins: str | list[str] = Field(
        validation_alias="FRONTEND_ORIGINS",
        description="Comma-separated list of allowed frontend origins",
    )

    @property
    def frontend_origins_list(self) -> list[str]:
        if isinstance(self.frontend_origins, str):
            return [self.frontend_origins]

        return self.frontend_origins

    # Database configuration (must be supplied via .env)
    # --------------------------------------------------------
    database_url: str
    test_database_url: str

    # GitHub OAuth configuration (must be overridden in .env)
    # --------------------------------------------------------
    github_client_id: str
    github_client_secret: str
    github_redirect_url: str
    github_state_secret_key: str

    # --- Token lifetimes ---
    lifetime_seconds: int = 3600

    # --- Cookie config ---
    cookie_name: str = "simboard_auth"
    cookie_secure: bool = False
    cookie_httponly: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_max_age: int = 3600


settings = Settings()
# Strip trailing slash from frontend_origin to prevent issues with CORS and
# redirects.
settings.frontend_origin = settings.frontend_origin.rstrip("/")
