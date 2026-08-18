"""Transcript domain models (Phase 3).

`Transcript` is the top-level, one-per-(conversation, source_media,
active-processing-run) record; `TranscriptSegment` rows are its ordered,
speaker-attributed, timestamped content — the output of alignment (ASR +
diarization), never raw unaligned ASR by itself once diarization ran.

Provenance chain preserved on every segment: transcript_id ->
speech_run_id / diarization_run_id / alignment_run_id (nullable — a
transcript with no diarization coverage still has valid
speech_run_id-only segments, `alignment_quality=UNASSIGNED`).

Immutability vs. correction (spec, "Transcript immutability vs.
correction"): `original_text` is the exact ASR/alignment output and is
NEVER overwritten. `corrected_text` is optional, human-entered, and only
present once a reviewer corrects the segment. `review_status` tracks the
per-segment review lifecycle. See app.transcription.corrections for the
audit trail of who changed what, when, from what previous value.

Word-level timing storage decision (see docs/architecture/adr/0016-word-timing-storage.md):
stored as a single validated JSON array per segment (`words`), not one row
per word. Segment counts are small (seconds-to-minutes granularity);
per-word tables would multiply row counts ~5-10x for no current query
benefit — Evidence/review only needs segment-level jump targets plus the
word list for future fine-grained highlighting, both served fine by JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class TranscriptStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class SegmentReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    FLAGGED = "flagged"


class AlignmentQuality(StrEnum):
    """Per-segment honesty flag from the alignment algorithm — never
    silently assign a speaker on weak temporal evidence. See
    app.transcription.alignment for how each value is produced."""

    CONFIDENT = "confident"
    AMBIGUOUS = "ambiguous"
    OVERLAP = "overlap"
    UNASSIGNED = "unassigned"


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_media_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The ProcessingRun (run_type=SPEECH_TO_TEXT) whose output this
    # transcript's segments were originally aligned from. Kept even after
    # diarization/alignment add speaker attribution.
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )

    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TranscriptStatus.PENDING.value, index=True
    )

    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # True once this transcript is the "active" one shown to users for its
    # source media (a reprocess creates a new Transcript row without
    # destroying the previous one — see app.processing.service.reprocess).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("detected_speakers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Original ASR/alignment output. NEVER overwritten by a correction.
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # provider_confidence: raw, provider-native confidence — never compared
    # cross-provider as if universally calibrated (see module docstring in
    # app.providers.speech_to_text).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Validated JSON array of {text, start_ms, end_ms, confidence} — see
    # module docstring "Word-level timing storage decision".
    words: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SegmentReviewStatus.UNREVIEWED.value, index=True
    )
    alignment_quality: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AlignmentQuality.UNASSIGNED.value
    )
    # Mechanical low-confidence/ambiguity review signal (spec: "Low-
    # confidence review foundation") — never an LLM/clinical judgement.
    review_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Full provenance, preserved even if the segment is later corrected.
    speech_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )
    diarization_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )
    alignment_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TranscriptSegmentCorrection(Base):
    """Audit trail for a single correction event on a segment — "record
    user/timestamp/previous-value" (spec). One row per correction, never
    updated in place."""

    __tablename__ = "transcript_segment_corrections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    segment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    corrected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    previous_corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
