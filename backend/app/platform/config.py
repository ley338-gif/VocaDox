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

    # -- Identity / sessions (Phase 1) --------------------------------------
    session_ttl_seconds: int = Field(
        default=43200,  # 12 hours
        description="Absolute session lifetime, enforced server-side via Valkey TTL.",
    )
    session_cookie_secure: bool = Field(
        default=True,
        description="Set the `Secure` cookie flag. Disable only for plain-HTTP local dev.",
    )

    # -- Media / conversation capture (Phase 2) ------------------------------
    max_upload_size_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024,  # 2 GiB — enough headroom for 120+ min WAV recordings.
        description="Hard cap on any single ingested media object (recording or file upload).",
    )
    allowed_audio_content_types: list[str] = Field(
        default_factory=lambda: [
            "audio/webm",
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "audio/mpeg",
            "audio/mp4",
            "audio/x-m4a",
        ],
        description="Content-Types accepted for audio ingestion. Never trusted alone — the "
        "backend also inspects magic bytes (see app.media.validation).",
    )
    upload_temp_dir: str = Field(
        default="./data/tmp-uploads",
        description="Controlled temp directory for spooled uploads before they are hashed, "
        "validated, and atomically moved into permanent storage.",
    )
    upload_timeout_seconds: int = Field(
        default=600,
        description="Server-side timeout for a single upload/finalize request.",
    )
    max_active_upload_sessions_per_user: int = Field(
        default=5,
        description="Cap on concurrent in-progress recording-upload sessions per user.",
    )
    recording_consent_notice: str = Field(
        default=(
            "Confirm that required consent/authorization for this recording has been obtained."
        ),
        description="Text shown in the recording consent step. Configurable per deployment. "
        "Displaying this notice does NOT itself make a recording legally compliant — consent "
        "and other legal obligations remain the deployment/operator's responsibility.",
    )
    default_retention_policy_name: str | None = Field(
        default=None,
        description="Name of the RetentionPolicy new conversations are assigned by default, "
        "if any. Unset means 'keep indefinitely' — an explicit choice, not a GDPR claim; "
        "operators should set this deliberately for production deployments.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
