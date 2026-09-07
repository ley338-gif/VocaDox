"""CRUD for KnownSpeaker, plus voiceprint enrollment (post-GA P1-2) — the
one place a KnownSpeaker's `voiceprint_embedding` is ever written, always
from an explicit human action (never inferred/auto-updated elsewhere).
Matching/suggestion logic itself lives in app.diarization.service (it
operates on DetectedSpeaker, not KnownSpeaker) and app.people.matching
(the pure similarity math).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.people.models import KnownSpeaker


class VoiceprintDimensionMismatchError(ValueError):
    """Raised when a new embedding's dimensionality doesn't match a
    KnownSpeaker's existing voiceprint (e.g. the diarization model was
    swapped for one with a different embedding size). Enrollment refuses
    to silently corrupt the running average in that case."""


async def list_known_speakers(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[KnownSpeaker]:
    result = await session.execute(
        select(KnownSpeaker)
        .where(KnownSpeaker.organization_id == organization_id)
        .order_by(KnownSpeaker.display_name)
    )
    return list(result.scalars().all())


async def create_known_speaker(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    display_name: str,
    notes: str | None,
    created_by_user_id: uuid.UUID | None,
) -> KnownSpeaker:
    known_speaker = KnownSpeaker(
        organization_id=organization_id,
        display_name=display_name,
        notes=notes,
        created_by_user_id=created_by_user_id,
    )
    session.add(known_speaker)
    await session.flush()
    return known_speaker


async def enroll_voiceprint(
    session: AsyncSession, known_speaker: KnownSpeaker, *, embedding: list[float]
) -> KnownSpeaker:
    """Folds one more sample into the KnownSpeaker's running-average
    voiceprint. Always an explicit human action (see app.diarization.
    router's enroll endpoint) — this function itself never decides *which*
    embedding to enroll, only how to combine it with what's already
    stored."""
    sample_count = known_speaker.voiceprint_sample_count
    existing = known_speaker.voiceprint_embedding
    if existing is None or sample_count == 0:
        new_embedding = list(embedding)
    else:
        if len(existing) != len(embedding):
            raise VoiceprintDimensionMismatchError(
                f"embedding dimension mismatch: existing voiceprint has {len(existing)} "
                f"dimensions, new sample has {len(embedding)}"
            )
        new_embedding = [
            (old * sample_count + new_val) / (sample_count + 1)
            for old, new_val in zip(existing, embedding, strict=True)
        ]
    known_speaker.voiceprint_embedding = new_embedding
    known_speaker.voiceprint_sample_count = sample_count + 1
    known_speaker.voiceprint_updated_at = datetime.now(UTC)
    await session.flush()
    return known_speaker
