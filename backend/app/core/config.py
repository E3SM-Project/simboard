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


def _normalize_list(items: list[str]) -> list[str]:
    """
    Normalize a list of strings by stripping whitespace and trailing slashes.

    Parameters
    ----------
    items : list[str]
        List of strings to normalize.

    Returns
    -------
    list[str]
        Normalized list of strings.
    """
    return [item.strip().rstrip("/") for item in items if item.strip()]


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
    domain: str = "example.com"

    # Frontend
    # ----------------------------------------
    # Primary frontend (used for redirects, links, emails, etc.)
    frontend_origin: str = Field(
        validation_alias="FRONTEND_ORIGIN",
        description="Primary frontend origin (staging or production)",
    )

    @property
    def frontend_origin_normalized(self) -> str:
        return self.frontend_origin.rstrip("/")

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
            origins = self.frontend_origins.strip().split(",")
        else:
            origins = self.frontend_origins

        return _normalize_list(origins)

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
