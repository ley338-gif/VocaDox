"""Read-side accessor for the active ModelProfile — the only place worker
code should learn "which model to use" (spec: no hardcoded model
identifiers in worker code)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.profiles.models import ModelProfile, ModelProfilePurpose


async def get_active_profile(
    session: AsyncSession, *, purpose: ModelProfilePurpose
) -> ModelProfile | None:
    result = await session.execute(
        select(ModelProfile)
        .where(ModelProfile.purpose == purpose.value, ModelProfile.enabled.is_(True))
        .order_by(ModelProfile.created_at.desc())
    )
    return result.scalars().first()
