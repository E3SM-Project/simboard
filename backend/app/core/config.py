from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # General application configuration
    # ----------------------------------------
    env: str = "development"
    port: int = 8000

    # Frontend
    # ----------------------------------------
    frontend_origin: str = "http://localhost:5173"

    # Database configuration (must be supplied via .env)
    # --------------------------------------------------------
    database_url: str = "postgresql://user:password@localhost:5432/defaultdb"

    # Used only for tests; must include "test" in the path.
    test_database_url: str = "postgresql://user:password@localhost:5432/defaultdb_test"

    # Security configuration (must be overridden in .env)
    # --------------------------------------------------------
    jwt_secret_key: str = "change_me_jwt_secret_key"
    reset_password_secret_key: str = "change_me_reset_secret_key"
    verification_secret_key: str = "change_me_verification_secret_key"


settings = Settings()
