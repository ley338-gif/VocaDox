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

    # -- Speech / diarization processing (Phase 3) ---------------------------
    speech_provider: str = Field(
        default="fake",
        description="'fake' (tests/dev, always available) or 'faster_whisper' (real, requires "
        "an installed model — see docs/admin/model-installation.md). Never defaults to a real "
        "provider so a fresh checkout without an installed model degrades safely.",
    )
    diarization_provider: str = Field(
        default="fake",
        description="'fake' (tests/dev) or 'pyannote' (real, requires an installed, "
        "license-accepted pyannote pipeline).",
    )
    model_volume_root: str = Field(
        default="./data/models",
        description="Persistent root for installed AI models (separate from conversation "
        "media — see docs/admin/model-installation.md). Never re-downloaded on restart.",
    )
    speech_model_dir_name: str = Field(default="speech-default")
    diarization_model_dir_name: str = Field(default="diarization-default")
    speech_device: str = Field(default="auto", description="'auto' | 'cuda' | 'cpu'")
    diarization_device: str = Field(default="auto", description="'auto' | 'cuda' | 'cpu'")
    huggingface_token: str | None = Field(
        default=None,
        description="Used only by the offline `vocadox models install` CLI to download a "
        "gated model (e.g. pyannote's pipeline) once, at admin-initiated install time. Never "
        "read by the API or worker request path, never logged, never exposed via any endpoint.",
    )
    # -- LLM / fact extraction (Phase 4) --------------------------------------
    llm_provider: str = Field(
        default="fake",
        description="'fake' (tests/dev, always available) or 'ollama' (real, requires a "
        "reachable local Ollama server with the configured model pulled — see "
        "docs/admin/llm-provider.md). Never defaults to a real provider so a fresh checkout "
        "without Ollama running degrades safely.",
    )
    llm_base_url: str = Field(
        default="http://ollama:11434",
        description="Base URL of the local Ollama server. Never a cloud/hosted endpoint — "
        "conversation content must never leave the deployment (spec: local-first LLM "
        "inference). Defaults to the Docker Compose service name; override with "
        "http://localhost:11434 for a host-run Ollama outside Compose.",
    )
    llm_model: str = Field(
        default="qwen2.5:14b",
        description="Ollama model tag for extraction. Apache-2.0 licensed (verified against "
        "the model's own Hugging Face license file — see compliance/model-inventory.yml and "
        "docs/architecture/adr/0024-llm-provider-selection.md). Never read by worker code "
        "directly for the actual extraction run — see app.profiles (ModelProfile); this "
        "setting only seeds the default profile row.",
    )
    llm_context_length: int = Field(default=32768)
    llm_max_tokens: int = Field(default=2048)
    llm_timeout_seconds: float = Field(default=300.0)

    normalization_target_sample_rate_hz: int = Field(default=16000)
    normalization_subprocess_timeout_seconds: int = Field(default=600)
    normalization_max_duration_seconds: int = Field(
        default=4 * 60 * 60, description="Hard cap on source media duration accepted for "
        "normalization (4 hours default)."
    )
    worker_concurrency: int = Field(
        default=1,
        description="Max concurrent GPU-heavy jobs per worker process. Safe default is 1 — "
        "see docs/admin/worker-configuration.md.",
    )
    job_lease_seconds: int = Field(
        default=300,
        description="How long a RUNNING job's lease is valid before another worker may "
        "reclaim it as abandoned (worker-crash recovery).",
    )
    max_active_processing_jobs_per_conversation: int = Field(
        default=3,
        description="Queue-fairness cap: a user cannot enqueue unlimited concurrent "
        "processing jobs for the same conversation.",
    )

    # -- Operations: Backup/Restore, Retention Cleanup (Phase 11) -----------
    backup_root: str = Field(
        default="./data/backups",
        description="Filesystem root each backup is written under, as its own "
        "`<backup_root>/<backup_id>/` directory (database.dump + media.tar). Deliberately "
        "separate from media_storage_root/model_volume_root (same 'don't mix storage "
        "purposes' principle as ADR-0011/Phase 3.1) — a real deployment should point this "
        "at a distinct volume/mount, ideally off-host, per docs/operations/disaster-recovery.md.",
    )
    pg_dump_path: str = Field(
        default="pg_dump", description="Path to the pg_dump binary (PostgreSQL License)."
    )
    pg_restore_path: str = Field(
        default="pg_restore", description="Path to the pg_restore binary (PostgreSQL License)."
    )
    psql_path: str = Field(
        default="psql", description="Path to the psql binary (PostgreSQL License)."
    )
    retention_cleanup_batch_size: int = Field(
        default=500,
        description="Max conversations evaluated per retention-cleanup run, to bound a single "
        "run's duration/lock footprint on a large deployment.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
