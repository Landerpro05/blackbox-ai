from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLACKBOX_", env_file=BACKEND_ROOT / ".env", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/blackbox.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    demo_testing_enabled: bool = False
    evidence_dir: Path = BACKEND_ROOT / "evidence"

    @field_validator("evidence_dir")
    @classmethod
    def resolve_evidence_directory(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_ROOT / value

    @model_validator(mode="after")
    def demo_is_local_only(self) -> "Settings":
        if self.demo_testing_enabled and self.environment == "production":
            raise ValueError(
                "La demostración solo está disponible en development/test."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
