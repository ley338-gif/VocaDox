"""SQLAlchemy ORM models for the media domain (Phase 2).

`MediaAsset` covers both original source media and derived (normalized)
media via `kind` — the row for a derived asset is a *new* row, never an
in-place mutation of the source row's bytes (see
docs/architecture/adr/0011-source-media-separation.md, "immutable source").
Audio-focused for Phase 2: not a generic file-storage / Dropbox feature.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.session import Base

if TYPE_CHECKING:
    from app.conversations.models import Conversation


class MediaKind(StrEnum):
    SOURCE_AUDIO = "source_audio"
    NORMALIZED_AUDIO = "normalized_audio"
    ATTACHMENT = "attachment"


class MediaSourceType(StrEnum):
    """Provenance of the bytes. Never fabricated — set exactly once, at
    ingestion, from how the bytes actually arrived."""

    BROWSER_RECORDING = "browser_recording"
    FILE_UPLOAD = "file_upload"
    API_UPLOAD = "api_upload"
    DERIVED = "derived"  # produced by a MediaNormalizer, not directly ingested


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Opaque key into StorageProvider — never a filesystem path exposed to
    # any API response.
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)

    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    container: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Immutability provenance: which source asset this derived asset was
    # normalized from. NULL for source assets themselves.
    derived_from_media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="media_assets")


class RecordingUploadStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ABORTED = "aborted"
    EXPIRED = "expired"


class RecordingUpload(Base):
    """A server-side session tracking a single in-progress recording
    upload from `POST /conversations/{id}/recordings` finalize flow.

    Phase 2 deliberately does NOT implement server-side chunk-by-chunk
    ingestion during recording (see
    docs/architecture/adr/0012-chunked-upload-decision.md for the full
    trade-off analysis) — the browser accumulates `MediaRecorder`
    `ondataavailable` chunks client-side and finalizes with a single
    streamed upload. This table exists so the *finalize* step is
    idempotent and auditable (same row reused on retry, never a duplicate
    MediaAsset on a repeated request) and so the architecture is ready to
    grow real chunk-by-chunk endpoints later without a schema change.
    """

    __tablename__ = "recording_uploads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RecordingUploadStatus.IN_PROGRESS.value
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expected_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    result_media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
