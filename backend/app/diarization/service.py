"""DetectedSpeaker/DiarizationSegment persistence + human speaker
assignment. Assignment is always an explicit human action recorded here —
never automatic, never voice-biometric identification (see
app.diarization.models module docstring).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diarization.models import DetectedSpeaker, DiarizationSegment
from app.providers.diarization import DiarizationResult


async def persist_diarization_result(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    diarization_run_id: uuid.UUID,
    result: DiarizationResult,
) -> dict[str, uuid.UUID]:
    """Creates one DetectedSpeaker per distinct provider label and one
    DiarizationSegment per turn. Overlap is detected here (a turn whose
    time range intersects another turn's range) and marked on both rows
    honestly rather than silently dropped. Returns {internal_label: id}."""
    label_to_speaker: dict[str, DetectedSpeaker] = {}
    for turn in result.turns:
        if turn.speaker_label not in label_to_speaker:
            speaker = DetectedSpeaker(
                conversation_id=conversation_id,
                diarization_run_id=diarization_run_id,
                internal_label=turn.speaker_label,
            )
            session.add(speaker)
            label_to_speaker[turn.speaker_label] = speaker
    await session.flush()

    turns_sorted = sorted(result.turns, key=lambda t: t.start_seconds)
    for turn in turns_sorted:
        is_overlap = any(
            other is not turn
            and turn.start_seconds < other.end_seconds
            and other.start_seconds < turn.end_seconds
            for other in turns_sorted
        )
        session.add(
            DiarizationSegment(
                diarization_run_id=diarization_run_id,
                speaker_id=label_to_speaker[turn.speaker_label].id,
                start_ms=int(round(turn.start_seconds * 1000)),
                end_ms=int(round(turn.end_seconds * 1000)),
                confidence=turn.confidence,
                is_overlap=is_overlap,
            )
        )
    await session.flush()
    return {label: speaker.id for label, speaker in label_to_speaker.items()}


async def list_speakers(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> list[DetectedSpeaker]:
    """Scoped to the diarization run(s) actually referenced by the
    conversation's currently *active* Transcript's segments — not every
    DetectedSpeaker ever created for this conversation.

    Reprocessing (see app.processing.orchestrator.start_transcription)
    never deletes prior DetectedSpeaker rows, matching this project's
    established never-destroy-processing-history principle — but that
    means a naive "all speakers for this conversation" query returns
    stale speakers from every earlier diarization run too, once a
    conversation has been reprocessed more than once. Found via manual
    testing: reprocessing a real 3-speaker recording with a corrected
    speaker-count hint left 5 speaker rows visible (2 stale + 3 current)
    instead of the real 3, and the rename-chip UI showed duplicate
    SPEAKER_00/SPEAKER_01 entries from the old run alongside the new
    one. `TranscriptSegment.diarization_run_id` is exactly the field
    Phase 3's alignment provenance work added for this kind of lookup.
    """
    from app.transcription.models import Transcript, TranscriptSegment

    run_ids_result = await session.execute(
        select(TranscriptSegment.diarization_run_id)
        .join(Transcript, Transcript.id == TranscriptSegment.transcript_id)
        .where(
            Transcript.conversation_id == conversation_id,
            Transcript.is_active.is_(True),
            TranscriptSegment.diarization_run_id.is_not(None),
        )
        .distinct()
    )
    active_run_ids = {row[0] for row in run_ids_result.all()}
    if not active_run_ids:
        # No diarization has ever completed for the active transcript
        # (e.g. diarize=False, or diarization hasn't finished yet) —
        # nothing to show, not "every speaker ever detected".
        return []

    result = await session.execute(
        select(DetectedSpeaker)
        .where(
            DetectedSpeaker.conversation_id == conversation_id,
            DetectedSpeaker.diarization_run_id.in_(active_run_ids),
        )
        .order_by(DetectedSpeaker.internal_label)
    )
    return list(result.scalars().all())


async def get_speaker(
    session: AsyncSession, *, conversation_id: uuid.UUID, speaker_id: uuid.UUID
) -> DetectedSpeaker | None:
    result = await session.execute(
        select(DetectedSpeaker).where(
            DetectedSpeaker.id == speaker_id, DetectedSpeaker.conversation_id == conversation_id
        )
    )
    return result.scalars().first()


async def assign_speaker(
    session: AsyncSession,
    speaker: DetectedSpeaker,
    *,
    participant_id: uuid.UUID | None,
    display_label: str | None,
    assigned_by_user_id: uuid.UUID | None,
) -> None:
    speaker.participant_id = participant_id
    speaker.display_label = display_label
    speaker.assigned_by_user_id = assigned_by_user_id
    speaker.assigned_at = datetime.now(UTC)
    await session.flush()


async def unassign_speaker(session: AsyncSession, speaker: DetectedSpeaker) -> None:
    speaker.participant_id = None
    speaker.display_label = None
    speaker.assigned_by_user_id = None
    speaker.assigned_at = None
    await session.flush()
