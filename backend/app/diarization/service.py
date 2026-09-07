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

from app.conversations.models import ConversationParticipant, ParticipantType
from app.diarization.models import DetectedSpeaker, DiarizationSegment
from app.people.matching import find_best_match
from app.people.models import KnownSpeaker
from app.providers.diarization import DiarizationResult


class SuggestionNotAvailableError(ValueError):
    """Raised by accept_suggestion when the speaker has no pending
    confidence-scored suggestion to accept."""


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
    embeddings = result.speaker_embeddings or {}
    label_to_speaker: dict[str, DetectedSpeaker] = {}
    for turn in result.turns:
        if turn.speaker_label not in label_to_speaker:
            speaker = DetectedSpeaker(
                conversation_id=conversation_id,
                diarization_run_id=diarization_run_id,
                internal_label=turn.speaker_label,
                embedding=embeddings.get(turn.speaker_label),
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


async def suggest_known_speakers(
    session: AsyncSession, *, organization_id: uuid.UUID, speaker_ids: list[uuid.UUID]
) -> None:
    """Post-GA P1-2: for each given DetectedSpeaker with a voice embedding,
    compares it against every enrolled KnownSpeaker voiceprint in the same
    organization and records the best match (if any clears the confidence
    threshold) as a *suggestion* — `suggested_known_speaker_id`/
    `suggested_confidence`. Never touches `participant_id`/`display_label`
    itself; turning a suggestion into a real assignment is always the
    separate, explicit `accept_suggestion` action."""
    speakers_result = await session.execute(
        select(DetectedSpeaker).where(DetectedSpeaker.id.in_(speaker_ids))
    )
    speakers = [s for s in speakers_result.scalars().all() if s.embedding is not None]
    if not speakers:
        return

    known_result = await session.execute(
        select(KnownSpeaker).where(
            KnownSpeaker.organization_id == organization_id,
            KnownSpeaker.voiceprint_embedding.is_not(None),
        )
    )
    candidates = {
        k.id: k.voiceprint_embedding
        for k in known_result.scalars().all()
        if k.voiceprint_embedding is not None
    }

    for speaker in speakers:
        assert speaker.embedding is not None  # narrowed by the filter above
        match = find_best_match(speaker.embedding, candidates) if candidates else None
        if match is None:
            speaker.suggested_known_speaker_id = None
            speaker.suggested_confidence = None
        else:
            speaker.suggested_known_speaker_id, speaker.suggested_confidence = match
    await session.flush()


async def accept_suggestion(
    session: AsyncSession,
    speaker: DetectedSpeaker,
    *,
    conversation_id: uuid.UUID,
    assigned_by_user_id: uuid.UUID | None,
) -> DetectedSpeaker:
    """Turns a pending confidence-scored suggestion into a real assignment
    — the explicit human accept step the suggestion mechanism requires.
    Reuses an existing participant already linked to the suggested
    KnownSpeaker on this conversation if one exists (created by an earlier
    accept, or by "remember as known person"), otherwise creates one."""
    if speaker.suggested_known_speaker_id is None:
        raise SuggestionNotAvailableError("speaker has no pending suggestion")
    known_speaker_id = speaker.suggested_known_speaker_id

    existing_result = await session.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.known_speaker_id == known_speaker_id,
        )
    )
    participant = existing_result.scalars().first()
    if participant is None:
        known_speaker = await session.get(KnownSpeaker, known_speaker_id)
        if known_speaker is None:
            raise SuggestionNotAvailableError("suggested known speaker no longer exists")
        participant = ConversationParticipant(
            conversation_id=conversation_id,
            display_name=known_speaker.display_name,
            participant_type=ParticipantType.UNKNOWN.value,
            known_speaker_id=known_speaker_id,
        )
        session.add(participant)
        await session.flush()

    await assign_speaker(
        session,
        speaker,
        participant_id=participant.id,
        display_label=participant.display_name,
        assigned_by_user_id=assigned_by_user_id,
    )
    return speaker
