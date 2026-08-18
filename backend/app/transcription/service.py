"""Transcript persistence/query service: idempotent transcript creation,
persisting aligned segments (the ALIGN stage's only writer), and human
correction (never overwrites `original_text` — spec, "Transcript
immutability vs. correction").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.transcription.alignment import AlignedSegment, AlignmentQuality
from app.transcription.models import (
    SegmentReviewStatus,
    Transcript,
    TranscriptSegment,
    TranscriptSegmentCorrection,
    TranscriptStatus,
)

LOW_CONFIDENCE_THRESHOLD = 0.55


async def get_active_transcript(
    session: AsyncSession, *, source_media_id: uuid.UUID
) -> Transcript | None:
    """The one active (non-terminal-or-ready) transcript row for this
    source, if any — used for job-idempotency checks."""
    result = await session.execute(
        select(Transcript).where(
            Transcript.source_media_id == source_media_id,
            Transcript.is_active.is_(True),
            Transcript.status.in_(
                [TranscriptStatus.PENDING.value, TranscriptStatus.PROCESSING.value]
            ),
        )
    )
    return result.scalars().first()


async def get_active_ready_transcript(
    session: AsyncSession, *, source_media_id: uuid.UUID
) -> Transcript | None:
    result = await session.execute(
        select(Transcript).where(
            Transcript.source_media_id == source_media_id,
            Transcript.is_active.is_(True),
            Transcript.status == TranscriptStatus.READY.value,
        )
    )
    return result.scalars().first()


async def create_transcript(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    source_media_id: uuid.UUID,
    provider: str,
    model: str,
    model_revision: str | None,
) -> Transcript:
    transcript = Transcript(
        conversation_id=conversation_id,
        source_media_id=source_media_id,
        provider=provider,
        model=model,
        model_revision=model_revision,
        status=TranscriptStatus.PENDING.value,
        is_active=True,
    )
    session.add(transcript)
    await session.flush()
    return transcript


async def mark_transcript_processing(
    session: AsyncSession, transcript: Transcript, *, processing_run_id: uuid.UUID, language: str
) -> None:
    transcript.status = TranscriptStatus.PROCESSING.value
    transcript.processing_run_id = processing_run_id
    transcript.language = language
    await session.flush()


async def mark_transcript_failed(
    session: AsyncSession, transcript: Transcript, *, error_code: str, error_message_safe: str
) -> None:
    transcript.status = TranscriptStatus.FAILED.value
    transcript.error_code = error_code
    transcript.error_message_safe = error_message_safe
    await session.flush()


def _review_flag(quality: AlignmentQuality, confidence: float | None) -> tuple[bool, str | None]:
    if quality == AlignmentQuality.OVERLAP:
        return True, "overlapping speech"
    if quality == AlignmentQuality.AMBIGUOUS:
        return True, "ambiguous speaker attribution"
    if quality == AlignmentQuality.UNASSIGNED:
        return True, "no diarization coverage"
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        return True, "low ASR confidence"
    return False, None


async def persist_aligned_segments(
    session: AsyncSession,
    transcript: Transcript,
    aligned: list[AlignedSegment],
    *,
    speech_run_id: uuid.UUID | None,
    diarization_run_id: uuid.UUID | None,
    alignment_run_id: uuid.UUID | None,
    speaker_label_to_id: dict[str, uuid.UUID],
) -> list[TranscriptSegment]:
    """The ALIGN stage's only writer of TranscriptSegment rows. Deletes any
    previously-persisted (uncorrected/unreviewed) segments for this
    transcript before writing the new set — safe because ALIGN always runs
    before a human has had a chance to review anything (no TranscriptSegment
    rows exist for a PENDING/PROCESSING transcript until this function
    runs). A reprocess creates a brand-new Transcript row instead of
    re-aligning an existing READY one, so this never touches a segment a
    human has corrected."""
    rows: list[TranscriptSegment] = []
    for i, seg in enumerate(aligned):
        review_flag, reason = _review_flag(seg.quality, seg.confidence)
        speaker_id = (
            speaker_label_to_id.get(seg.speaker_label) if seg.speaker_label is not None else None
        )
        row = TranscriptSegment(
            transcript_id=transcript.id,
            speaker_id=speaker_id,
            sequence=i,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            original_text=seg.text,
            corrected_text=None,
            confidence=seg.confidence,
            words=[
                {
                    "text": w.text,
                    "start_ms": w.start_ms,
                    "end_ms": w.end_ms,
                    "confidence": w.confidence,
                }
                for w in seg.words
            ]
            or None,
            review_status=SegmentReviewStatus.UNREVIEWED.value,
            alignment_quality=seg.quality.value,
            review_flag=review_flag,
            review_flag_reason=reason,
            speech_run_id=speech_run_id,
            diarization_run_id=diarization_run_id,
            alignment_run_id=alignment_run_id,
        )
        session.add(row)
        rows.append(row)

    transcript.status = TranscriptStatus.READY.value
    await session.flush()
    return rows


async def list_segments(
    session: AsyncSession, *, transcript_id: uuid.UUID
) -> list[TranscriptSegment]:
    result = await session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.sequence)
    )
    return list(result.scalars().all())


async def correct_segment(
    session: AsyncSession,
    segment: TranscriptSegment,
    *,
    new_text: str,
    user_id: uuid.UUID | None,
) -> TranscriptSegmentCorrection:
    """Never overwrites `original_text`. Records a correction audit row
    with the previous corrected value (which may be None on the first
    correction) before applying the new one."""
    correction = TranscriptSegmentCorrection(
        segment_id=segment.id,
        corrected_by_user_id=user_id,
        previous_corrected_text=segment.corrected_text,
        new_corrected_text=new_text,
    )
    session.add(correction)
    segment.corrected_text = new_text
    segment.review_status = SegmentReviewStatus.CORRECTED.value
    await session.flush()
    return correction


async def set_review_status(
    session: AsyncSession, segment: TranscriptSegment, *, status: SegmentReviewStatus
) -> None:
    segment.review_status = status.value
    await session.flush()


async def now_utc() -> datetime:  # small seam for testability
    return datetime.now(UTC)
