"""Application configuration.

All configuration is sourced from environment variables (see
`deploy/.env.example` for the full list). No secrets are hardcoded and no
values are logged at startup beyond non-sensitive metadata.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings, loaded once and cached."""

    model_config = SettingsConfigDict(
        env_prefix="VOCADOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VocaDox"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", description="'json' or 'console'")

    api_prefix: str = "/api/v1"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = Field(
        default="postgresql+asyncpg://vocadox:vocadox@localhost:5432/vocadox",
        description="Async SQLAlchemy connection string (asyncpg driver).",
    )
    database_echo: bool = False

    valkey_url: str = Field(default="valkey://localhost:6379/0")

    media_storage_root: str = Field(
        default="./data/media",
        description="Filesystem root for LocalFilesystemStorage (Phase 0 provider).",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
