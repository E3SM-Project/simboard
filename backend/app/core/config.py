from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
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
