"""Idempotent bootstrap for the default extraction `ModelProfile` row —
mirrors app.identity.seed's pattern exactly. Reads Settings only at seed
time (never at extraction time — the worker always reads the DB row, see
app.profiles.service.get_active_profile), so an admin can change the
active model by editing the row without redeploying code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.config import get_settings
from app.profiles.models import ModelProfile, ModelProfilePurpose


async def apply_seed(session: AsyncSession) -> None:
    settings = get_settings()
    existing = await session.execute(
        select(ModelProfile).where(ModelProfile.purpose == ModelProfilePurpose.EXTRACTION.value)
    )
    if existing.scalars().first() is not None:
        return

    provider = settings.llm_provider
    model_identifier = settings.llm_model if provider != "fake" else "fake-llm-v0"
    session.add(
        ModelProfile(
            name="Default Extraction Model",
            purpose=ModelProfilePurpose.EXTRACTION.value,
            provider=provider,
            model_identifier=model_identifier,
            context_length=settings.llm_context_length,
            temperature=0.0,
            max_tokens=settings.llm_max_tokens,
            structured_output=True,
            version="1",
            enabled=True,
        )
    )
    await session.flush()


async def _reseed_cli() -> int:  # pragma: no cover - trivial CLI wrapper
    from app.platform.db import model_registry  # noqa: F401
    from app.platform.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()
    print("Model profile seed applied (created if none existed).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_reseed_cli()))
