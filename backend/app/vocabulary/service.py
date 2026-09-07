"""Custom vocabulary CRUD + resolution (post-GA P0-3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.vocabulary.models import VocabularyEntry


async def list_vocabulary(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[VocabularyEntry]:
    result = await session.execute(
        select(VocabularyEntry)
        .where(VocabularyEntry.organization_id == organization_id)
        .order_by(VocabularyEntry.created_at.asc())
    )
    return list(result.scalars().all())


async def get_vocabulary(
    session: AsyncSession, *, organization_id: uuid.UUID, entry_id: uuid.UUID
) -> VocabularyEntry | None:
    result = await session.execute(
        select(VocabularyEntry).where(
            VocabularyEntry.id == entry_id, VocabularyEntry.organization_id == organization_id
        )
    )
    return result.scalar_one_or_none()


class DuplicateVocabularyScopeError(ValueError):
    """Raised when an organization already has a `VocabularyEntry` for
    the same (organization_id, template_id) pair -- at most one entry
    per scope, matching `uq_vocabulary_org_template`."""


async def _assert_scope_free(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    template_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    stmt = select(VocabularyEntry.id).where(
        VocabularyEntry.organization_id == organization_id,
        VocabularyEntry.template_id == template_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(VocabularyEntry.id != exclude_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise DuplicateVocabularyScopeError(
            "a vocabulary entry for this organization/template already exists"
        )


async def create_vocabulary(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    template_id: uuid.UUID | None,
    name: str,
    terms: list[str],
    initial_prompt: str | None,
    created_by_user_id: uuid.UUID | None,
) -> VocabularyEntry:
    await _assert_scope_free(session, organization_id=organization_id, template_id=template_id)
    entry = VocabularyEntry(
        organization_id=organization_id,
        template_id=template_id,
        name=name,
        terms=terms,
        initial_prompt=initial_prompt,
        created_by_user_id=created_by_user_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def delete_vocabulary(session: AsyncSession, entry: VocabularyEntry) -> None:
    await session.delete(entry)
    await session.flush()


async def resolve_vocabulary(
    session: AsyncSession, *, organization_id: uuid.UUID, template_id: uuid.UUID | None
) -> VocabularyEntry | None:
    """Most specific first: an entry scoped to this exact
    (organization, template) wins; otherwise fall back to the
    organization-wide entry (`template_id IS NULL`); otherwise no
    vocabulary applies -- transcription proceeds exactly as before this
    feature existed."""
    if template_id is not None:
        result = await session.execute(
            select(VocabularyEntry).where(
                VocabularyEntry.organization_id == organization_id,
                VocabularyEntry.template_id == template_id,
            )
        )
        entry = result.scalar_one_or_none()
        if entry is not None:
            return entry

    result = await session.execute(
        select(VocabularyEntry).where(
            VocabularyEntry.organization_id == organization_id,
            VocabularyEntry.template_id.is_(None),
        )
    )
    return result.scalar_one_or_none()


def vocabulary_to_hotwords(entry: VocabularyEntry | None) -> str | None:
    """faster-whisper's `hotwords` parameter is a single string, not a
    list -- joins the structured `terms` the same way an admin would type
    them by hand."""
    if entry is None or not entry.terms:
        return None
    return " ".join(entry.terms)
