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
    deployment_mode: Literal["local", "https"] = "local"
    api_hosts: list[str] = Field(
        default=["127.0.0.1", "localhost", "::1"], min_length=1, max_length=10
    )
    session_hours: int = Field(default=8, ge=1, le=24)
    session_idle_minutes: int = Field(default=60, ge=5, le=120)
    auth_attempts: int = Field(default=5, ge=2, le=20)
    auth_window_seconds: int = Field(default=900, ge=30, le=3600)
    api_requests_per_minute: int = Field(default=300, ge=30, le=2000)
    max_body_bytes: int = Field(default=65536, ge=4096, le=262144)
    body_timeout_seconds: int = Field(default=10, ge=1, le=30)
    audit_retention_days: int = Field(default=90, ge=7, le=365)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    demo_testing_enabled: bool = False
    local_lab_enabled: bool = False
    local_lab_allowed_origins: list[str] = Field(default_factory=list, max_length=5)
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

    @field_validator("local_lab_allowed_origins")
    @classmethod
    def exact_origins(cls, values: list[str]) -> list[str]:
        from app.testing.local_policy import local_origin

        return sorted({local_origin(value, True) for value in values})

    @model_validator(mode="after")
    def demo_is_local_only(self) -> "Settings":
        import re
        from urllib.parse import urlsplit

        for host in self.api_hosts:
            if not re.fullmatch(r"(?:[A-Za-z0-9.-]+|::1)", host) or "*" in host:
                raise ValueError(
                    "Configura hosts de API exactos, sin esquemas ni comodines."
                )
            if self.deployment_mode == "local" and host not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("El modo local solo admite hosts de loopback.")

        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError(
                    "Configura orígenes CORS exactos sin credenciales ni rutas."
                )
            if self.deployment_mode == "local" and parsed.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError(
                    "El modo local solo permite orígenes CORS de loopback."
                )
            if self.deployment_mode == "https" and parsed.scheme != "https":
                raise ValueError(
                    "El modo no local requiere orígenes HTTPS y cookies Secure."
                )
        if self.environment == "production" and self.deployment_mode != "https":
            raise ValueError(
                "Production requiere HTTPS y cookies Secure; no habilita despliegue público."
            )
        if (
            self.demo_testing_enabled or self.local_lab_enabled
        ) and self.environment == "production":
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
