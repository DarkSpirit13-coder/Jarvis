"""Typed runtime configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and production-safe defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "JARVIS"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", pattern="^(development|test|staging|production)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    enable_openapi: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: PostgresDsn = "postgresql+asyncpg://jarvis:jarvis@postgres:5432/jarvis"
    redis_url: RedisDsn = "redis://redis:6379/0"

    jwt_secret_key: str = Field(default="development-secret-change-before-production", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.5"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2048, ge=128, le=32768)
    llm_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    tool_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    tool_retries: int = Field(default=1, ge=0, le=5)
    terminal_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    workspace_root: str = "."

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Normalize comma-delimited CORS origins into a list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
