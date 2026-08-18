"""Diarization domain models (Phase 3).

`DetectedSpeaker` is deliberately separate from `ConversationParticipant`
(spec, "Detected Speakers"): it represents a diarization-run-scoped
machine-detected voice cluster (`internal_label`, e.g. "SPEAKER_00"), not
a real identified person. Mapping a DetectedSpeaker to a real
`ConversationParticipant` (or a free-form `display_label`) is always an
explicit human action recorded here — never automatic, never voice
biometric identification.

`DiarizationSegment` rows are the raw normalized diarization-provider
output (see app.providers.diarization.DiarizationResult) persisted for
provenance/replay; `TranscriptSegment.speaker_id` (set by alignment) is
the user-facing result. Diarization may report overlapping speaker turns
— this is represented honestly via `is_overlap`, not hidden.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class DetectedSpeaker(Base):
    __tablename__ = "detected_speakers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    diarization_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )

    internal_label: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "SPEAKER_00"
    display_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Human-controlled mapping only, set via PATCH .../speakers/{id}. Never
    # inferred automatically, never a voice-biometric identity match.
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversation_participants.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DiarizationSegment(Base):
    """Raw diarization-provider turn, one row per turn (kept even where a
    later turn overlaps a previous one in time — see `is_overlap`)."""

    __tablename__ = "diarization_segments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    diarization_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("detected_speakers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_overlap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
