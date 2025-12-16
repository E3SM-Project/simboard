from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path


def get_env_file(project_root: Path | None = None) -> str:
    """
    Determine which environment-specific .env file to load.

    Uses APP_ENV to select one of:
        * .envs/dev/backend.env
        * .envs/dev_docker/backend.env
        * .envs/prod/backend.env

    Defaults to `.envs/dev/backend.env` when APP_ENV is not set.
    Ignores any .example files.
    """
    app_env = os.getenv("APP_ENV", "dev")

    if project_root is None:
        project_root = Path(__file__).resolve().parents[3]

    env_file = project_root / ".envs" / app_env / "backend.env"

    if env_file.name.endswith(".example"):
        raise FileNotFoundError("Refusing to load .example env files.")

    if not env_file.exists():
        raise FileNotFoundError(f"Environment file '{env_file}' does not exist.")

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

    # Frontend
    # ----------------------------------------
    frontend_origin: str = "https://127.0.0.1:5173"
    frontend_auth_redirect_url: str = "https://127.0.0.1:5173/auth/callback"

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
