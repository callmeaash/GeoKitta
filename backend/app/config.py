from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App settings, read from environment variables or the project's .env file."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "GeoKitta"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/geokitta"
    cors_origins: list[str] = ["http://localhost:5173"]
    jwt_secret: str = ""  # required for officer login; see .env.example
    session_hours: int = 8
    cookie_secure: bool = False  # set true when served over HTTPS


settings = Settings()
