"""Template/Prompt CRUD + versioning service. Publishing is the only way a
template/prompt's content ever changes for real consumers — this module
never lets a route mutate a PUBLISHED or RETIRED version's content (the ORM
`before_update` guards in app.templates.models are the hard enforcement;
this module just never attempts it)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.identity.models import User
from app.templates.models import (
    Prompt,
    PromptVersion,
    Template,
    TemplateVersion,
    VersionLifecycleStatus,
    transition_version_status,
)

DEFAULT_TEMPLATE_KEY = "general"


class TemplateNotFoundError(ValueError):
    pass


class NoPublishedVersionError(ValueError):
    pass


# -- Templates ---------------------------------------------------------------


async def get_template_by_key(session: AsyncSession, key: str) -> Template | None:
    result = await session.execute(select(Template).where(Template.key == key))
    return result.scalar_one_or_none()


async def list_templates(session: AsyncSession) -> list[Template]:
    result = await session.execute(select(Template).order_by(Template.key.asc()))
    return list(result.scalars().all())


async def get_published_version(session: AsyncSession, template: Template) -> TemplateVersion:
    if template.current_published_version_id is None:
        raise NoPublishedVersionError(f"template {template.key!r} has no published version")
    version = await session.get(TemplateVersion, template.current_published_version_id)
    if version is None:  # pragma: no cover - FK integrity guards this in practice
        raise NoPublishedVersionError(f"template {template.key!r} has no published version")
    return version


async def get_default_template_version(session: AsyncSession) -> TemplateVersion:
    """The "SYSTEM DEFAULT" layer's template — what extraction/composition
    falls back to when no ProcessingProfile/conversation override names a
    different one. Always the "general" template's published version."""
    template = await get_template_by_key(session, DEFAULT_TEMPLATE_KEY)
    if template is None:  # pragma: no cover - seeded at startup, defensive only
        raise TemplateNotFoundError("default 'general' template is not seeded")
    return await get_published_version(session, template)


async def list_template_versions(
    session: AsyncSession, template_id: uuid.UUID
) -> list[TemplateVersion]:
    result = await session.execute(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version_number.asc())
    )
    return list(result.scalars().all())


async def create_template(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None,
    extraction_categories: list[dict[str, Any]],
    presentation: list[dict[str, Any]],
    review_rules: dict[str, Any] | None,
    created_by: User,
) -> Template:
    template = Template(key=key, name=name, description=description)
    session.add(template)
    await session.flush()
    version = TemplateVersion(
        template_id=template.id,
        version_number=1,
        status=VersionLifecycleStatus.DRAFT.value,
        extraction_categories=extraction_categories,
        presentation=presentation,
        review_rules=review_rules,
        created_by_user_id=created_by.id if created_by else None,
    )
    session.add(version)
    await session.flush()
    return template


async def create_draft_version(
    session: AsyncSession,
    *,
    template: Template,
    extraction_categories: list[dict[str, Any]],
    presentation: list[dict[str, Any]],
    review_rules: dict[str, Any] | None,
    created_by: User,
) -> TemplateVersion:
    """Never mutates an existing version — always a brand new DRAFT row,
    numbered one past the highest version_number this template has ever
    had (even a RETIRED one), matching Phase 5's revision-numbering
    precedent (`app.documents.service.compose_document`)."""
    existing = await list_template_versions(session, template.id)
    next_number = (max((v.version_number for v in existing), default=0)) + 1
    version = TemplateVersion(
        template_id=template.id,
        version_number=next_number,
        status=VersionLifecycleStatus.DRAFT.value,
        extraction_categories=extraction_categories,
        presentation=presentation,
        review_rules=review_rules,
        created_by_user_id=created_by.id if created_by else None,
    )
    session.add(version)
    await session.flush()
    return version


async def publish_template_version(
    session: AsyncSession,
    *,
    template: Template,
    version: TemplateVersion,
    published_by: User | None,
) -> TemplateVersion:
    """Publishing NEVER mutates the previously-published version's content
    — it only flips its `status` to RETIRED (the content columns are frozen
    by the ORM guard the instant a version leaves DRAFT/TEST) and re-points
    `template.current_published_version_id` at the new one. Every existing
    reference to the old version's id (a past ProcessingRun/DocumentRevision)
    keeps resolving to the exact, unchanged content it was composed with."""
    version.status = transition_version_status(
        VersionLifecycleStatus(version.status), VersionLifecycleStatus.PUBLISHED
    ).value
    version.published_at = datetime.now(UTC)
    await session.flush()

    if template.current_published_version_id is not None:
        previous = await session.get(TemplateVersion, template.current_published_version_id)
        if previous is not None and previous.id != version.id:
            previous.status = VersionLifecycleStatus.RETIRED.value
            previous.retired_at = datetime.now(UTC)
            await session.flush()

    template.current_published_version_id = version.id
    await session.flush()

    await record_event(
        session,
        event_type="template.published",
        user_id=published_by.id if published_by else None,
        event_metadata={
            "template_id": str(template.id),
            "template_key": template.key,
            "template_version_id": str(version.id),
            "version_number": version.version_number,
        },
    )
    return version


# -- Prompts -------------------------------------------------------------


async def get_prompt_by_key(session: AsyncSession, key: str) -> Prompt | None:
    result = await session.execute(select(Prompt).where(Prompt.key == key))
    return result.scalar_one_or_none()


async def list_prompts(session: AsyncSession) -> list[Prompt]:
    result = await session.execute(select(Prompt).order_by(Prompt.key.asc()))
    return list(result.scalars().all())


async def list_prompt_versions(session: AsyncSession, prompt_id: uuid.UUID) -> list[PromptVersion]:
    result = await session.execute(
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version_number.asc())
    )
    return list(result.scalars().all())


async def get_published_prompt_version(
    session: AsyncSession, prompt: Prompt
) -> PromptVersion | None:
    if prompt.current_published_version_id is None:
        return None
    return await session.get(PromptVersion, prompt.current_published_version_id)


async def create_prompt(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    purpose: str,
    system_prompt: str,
    category_instructions: dict[str, str],
    created_by: User | None,
) -> Prompt:
    prompt = Prompt(key=key, name=name, purpose=purpose)
    session.add(prompt)
    await session.flush()
    version = PromptVersion(
        prompt_id=prompt.id,
        version_number=1,
        status=VersionLifecycleStatus.DRAFT.value,
        system_prompt=system_prompt,
        category_instructions=category_instructions,
        created_by_user_id=created_by.id if created_by else None,
    )
    session.add(version)
    await session.flush()
    return prompt


async def create_draft_prompt_version(
    session: AsyncSession,
    *,
    prompt: Prompt,
    system_prompt: str,
    category_instructions: dict[str, str],
    created_by: User,
) -> PromptVersion:
    existing = await list_prompt_versions(session, prompt.id)
    next_number = (max((v.version_number for v in existing), default=0)) + 1
    version = PromptVersion(
        prompt_id=prompt.id,
        version_number=next_number,
        status=VersionLifecycleStatus.DRAFT.value,
        system_prompt=system_prompt,
        category_instructions=category_instructions,
        created_by_user_id=created_by.id if created_by else None,
    )
    session.add(version)
    await session.flush()
    return version


async def publish_prompt_version(
    session: AsyncSession, *, prompt: Prompt, version: PromptVersion, published_by: User | None
) -> PromptVersion:
    version.status = transition_version_status(
        VersionLifecycleStatus(version.status), VersionLifecycleStatus.PUBLISHED
    ).value
    version.published_at = datetime.now(UTC)
    await session.flush()

    if prompt.current_published_version_id is not None:
        previous = await session.get(PromptVersion, prompt.current_published_version_id)
        if previous is not None and previous.id != version.id:
            previous.status = VersionLifecycleStatus.RETIRED.value
            previous.retired_at = datetime.now(UTC)
            await session.flush()

    prompt.current_published_version_id = version.id
    await session.flush()

    await record_event(
        session,
        event_type="prompt.published",
        user_id=published_by.id if published_by else None,
        event_metadata={
            "prompt_id": str(prompt.id),
            "prompt_key": prompt.key,
            "prompt_version_id": str(version.id),
            "version_number": version.version_number,
        },
    )
    return version
