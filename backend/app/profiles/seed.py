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


async def apply_processing_profile_seed(session: AsyncSession) -> None:
    """Idempotent bootstrap for Phase 6's two initial, real, end-user-
    selectable Processing Profiles (spec §19): "General" (the SYSTEM
    DEFAULT layer's fallback — see app.profiles.resolver) and "Meeting".
    Must run AFTER `app.templates.seed.apply_seed` (needs the general/
    meeting templates' published versions to exist) and this module's own
    `apply_seed` (needs the extraction ModelProfile to exist)."""
    from app.profiles.service import (
        create_processing_profile,
        get_processing_profile_by_key,
        list_processing_profile_versions,
        publish_processing_profile_version,
    )
    from app.templates.models import TemplateVersion
    from app.templates.service import (
        get_default_template_version,
        get_prompt_by_key,
        get_template_by_key,
    )

    extraction_result = await session.execute(
        select(ModelProfile).where(ModelProfile.purpose == ModelProfilePurpose.EXTRACTION.value)
    )
    extraction_profile = extraction_result.scalars().first()

    async def _seed_processing_profile(
        *, key: str, name: str, description: str, template_key: str, is_default: bool
    ) -> None:
        if await get_processing_profile_by_key(session, key) is not None:
            return
        template_version: TemplateVersion
        if template_key == "general":
            template_version = await get_default_template_version(session)
        else:
            template = await get_template_by_key(session, template_key)
            if template is None or template.current_published_version_id is None:
                return  # foundation-only template, not yet publishable as a profile
            maybe_version = await session.get(
                TemplateVersion, template.current_published_version_id
            )
            assert maybe_version is not None
            template_version = maybe_version

        prompt = await get_prompt_by_key(session, f"extraction-{template_key}")

        profile = await create_processing_profile(
            session,
            key=key,
            name=name,
            description=description,
            is_system_default=is_default,
            created_by=None,
            speech_provider_config=None,
            diarization_provider_config=None,
            extraction_model_profile_id=extraction_profile.id if extraction_profile else None,
            document_model_profile_id=None,
            template_id=template_version.template_id,
            template_version_id=template_version.id,
            prompt_id=prompt.id if prompt else None,
            prompt_version_id=(
                prompt.current_published_version_id
                if prompt is not None and prompt.current_published_version_id
                else None
            ),
            language="auto",
            retention_policy_id=None,
        )
        versions = await list_processing_profile_versions(session, profile.id)
        await publish_processing_profile_version(
            session, profile=profile, version=versions[0], published_by=None
        )

    await _seed_processing_profile(
        key="general",
        name="General",
        description="Domain-neutral conversations: general facts, decisions, tasks/follow-ups.",
        template_key="general",
        is_default=True,
    )
    await _seed_processing_profile(
        key="meeting",
        name="Meeting",
        description="Agenda topics, decisions with rationale, action items with owner/due date.",
        template_key="meeting",
        is_default=False,
    )


async def _reseed_cli() -> int:  # pragma: no cover - trivial CLI wrapper
    from app.platform.db import model_registry  # noqa: F401
    from app.platform.db.session import get_sessionmaker
    from app.templates.seed import apply_seed as apply_template_seed

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_seed(session)
        await apply_template_seed(session)
        await apply_processing_profile_seed(session)
        await session.commit()
    print("Model/template/processing profile seed applied (created if none existed).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_reseed_cli()))
