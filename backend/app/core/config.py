from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    ai_provider: Literal["disabled", "anthropic"] = "disabled"
    ai_model: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9._:-]*$")
    ai_api_key: SecretStr | None = None
    ai_timeout_seconds: int = Field(default=30, ge=5, le=60)
    ai_max_retries: int = Field(default=1, ge=0, le=1)
    ai_max_output_tokens: int = Field(default=2000, ge=256, le=3000)
    ai_daily_call_limit: int = Field(default=10, ge=1, le=100)
    ai_run_call_limit: int = Field(default=2, ge=1, le=5)
    ai_daily_token_limit: int = Field(default=100000, ge=1000, le=1000000)
    ai_cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    ai_input_usd_per_million: float | None = Field(
        default=None, ge=0, le=10000, allow_inf_nan=False
    )
    ai_output_usd_per_million: float | None = Field(
        default=None, ge=0, le=10000, allow_inf_nan=False
    )
    ai_daily_budget_usd: float | None = Field(
        default=None, gt=0, le=1000, allow_inf_nan=False
    )

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
        if self.ai_daily_budget_usd is not None and (
            self.ai_input_usd_per_million is None
            or self.ai_output_usd_per_million is None
        ):
            raise ValueError(
                "El presupuesto de IA requiere ambas tarifas por millón de tokens."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
