import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file(project_root: Path | None = None) -> str | None:
    """Determine which environment-specific .env file to load.

    Behavior:
        - In CI (CI=true), rely solely on environment variables.
        - Otherwise, require `.envs/<APP_ENV>/backend.env`.

    This avoids brittle heuristics based on partial env var presence.

    Parameters
    ----------
    project_root : Path or None, optional
        The root directory of the project. If None, it is inferred from the file
        location.

    Returns
    -------
    str or None
        The path to the environment file as a string, or None if running in CI.

    Raises
    ------
    FileNotFoundError
        If the required environment file does not exist.
    """
    # In CI, do not require an env file
    if os.getenv("CI", "").lower() == "true":
        return None

    app_env = os.getenv("APP_ENV", "dev")

    if project_root is None:
        project_root = Path(__file__).resolve().parents[3]

    env_file = project_root / ".envs" / app_env / "backend.env"

    if not env_file.exists():
        raise FileNotFoundError(
            f"Environment file '{env_file}' does not exist. "
            "Create it or set CI=true to rely on environment variables."
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
