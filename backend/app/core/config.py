from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLACKBOX_", env_file=BACKEND_ROOT / ".env", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/blackbox.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
