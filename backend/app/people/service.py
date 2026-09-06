"""CRUD for KnownSpeaker — deliberately thin (no matching/suggestion logic
here; see app/people/__init__.py for why automatic matching is deferred).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.people.models import KnownSpeaker


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
