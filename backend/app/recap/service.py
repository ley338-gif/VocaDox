"""Recap generation/approval. Unlike app.documents.service.compose_document
(deterministic, no LLM), this makes a real `LLMProvider.complete()` call —
see app/recap/__init__.py for why that's a legitimate, disclosed exception
scoped to this separate artifact type, not a relaxation of the Document
domain's own hard constraint.

Deliberately synchronous (called inline from the request handler, like
Document composition) rather than queued through a ProcessingJob/worker —
a single narrative completion over an already-short, already-composed
Document is much lighter than the multi-category extraction loop that
justifies Extraction's job-queue treatment. If this proves too slow in
practice for real hardware, moving it to the worker queue is a
contained follow-up (see the module docstring's own disclosure norm).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentRevision
from app.identity.models import User
from app.providers.llm import LLMProvider
from app.recap.models import Recap, RecapRevision, RecapShareLink, RecapStatus
from app.recap.prompts import SYSTEM_PROMPT, build_prompt
from app.transcription.models import Transcript

# Bounded so a share link can never be effectively permanent -- an admin
# picks from a small set of concrete durations (see the router's request
# schema), not an arbitrary value.
MAX_SHARE_LINK_TTL_HOURS = 30 * 24


class RecapNotComposableError(RuntimeError):
    """Raised when a conversation has no composed Document yet — a Recap
    is always derived from the Document's already-fact-checked content,
    never directly from the raw transcript."""


class RecapApprovalError(RuntimeError):
    """Raised when approval is attempted on a Recap with no DRAFT
    revision to approve."""


async def _load_document_text(session: AsyncSession, conversation_id: uuid.UUID) -> str:
    result = await session.execute(
        select(Document).where(Document.conversation_id == conversation_id)
    )
    document = result.scalar_one_or_none()
    if document is None or document.current_revision_id is None:
        raise RecapNotComposableError(
            "no document composed yet for this conversation — compose the document first"
        )
    revision = await session.get(DocumentRevision, document.current_revision_id)
    assert revision is not None
    return revision.rendered_text


async def _load_language(session: AsyncSession, conversation_id: uuid.UUID) -> str | None:
    """Non-destructive reprocessing (see app.transcription) keeps prior
    Transcript rows around instead of deleting them, so a conversation can
    have more than one — `is_active` marks the current one, mirroring
    app.transcription.router._get_transcript_or_404."""
    result = await session.execute(
        select(Transcript.language).where(
            Transcript.conversation_id == conversation_id, Transcript.is_active.is_(True)
        )
    )
    return result.scalar_one_or_none()


async def generate_recap(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    provider: LLMProvider,
    requested_by: User,
) -> Recap:
    """Always creates a NEW RecapRevision — never mutates an existing one
    (mirrors app.documents.service.compose_document)."""
    document_text = await _load_document_text(session, conversation_id)
    language = await _load_language(session, conversation_id)

    response = await provider.complete(build_prompt(document_text), system_prompt=SYSTEM_PROMPT)

    result = await session.execute(select(Recap).where(Recap.conversation_id == conversation_id))
    recap = result.scalar_one_or_none()
    if recap is None:
        recap = Recap(conversation_id=conversation_id, status=RecapStatus.DRAFT.value)
        session.add(recap)
        await session.flush()

    max_revision_result = await session.execute(
        select(RecapRevision.revision_number)
        .where(RecapRevision.recap_id == recap.id)
        .order_by(RecapRevision.revision_number.desc())
    )
    last_number = max_revision_result.scalars().first() or 0

    revision = RecapRevision(
        recap_id=recap.id,
        revision_number=last_number + 1,
        content=response.text,
        language=language,
        provider=provider.status().provider,
        model_identifier=response.model_name,
        status=RecapStatus.DRAFT.value,
        created_by_user_id=requested_by.id,
    )
    session.add(revision)
    await session.flush()

    recap.current_revision_id = revision.id
    recap.status = RecapStatus.DRAFT.value
    await session.flush()
    return recap


async def approve_recap(session: AsyncSession, *, recap: Recap, approved_by: User) -> Recap:
    """Only ever reachable from a route requiring `recap:approve` — the AI
    never calls this."""
    if recap.current_revision_id is None:
        raise RecapApprovalError("no revision to approve")
    revision = await session.get(RecapRevision, recap.current_revision_id)
    assert revision is not None
    if revision.status != RecapStatus.DRAFT.value:
        raise RecapApprovalError(f"revision is '{revision.status}', not draft")

    revision.status = RecapStatus.APPROVED.value
    revision.approved_by_user_id = approved_by.id
    revision.approved_at = datetime.now(UTC)
    recap.status = RecapStatus.APPROVED.value
    await session.flush()
    return recap


# -- Share links (post-GA P3-2) ----------------------------------------


class ShareLinkNotAvailableError(RuntimeError):
    """Raised when a share link is requested for a recap that isn't
    currently approved -- matches export_recap_endpoint's own "must be
    approved" gate; sharing something not yet approved would defeat the
    point of the approval step."""


async def create_share_link(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    recap: Recap,
    ttl_hours: int,
    created_by_user_id: uuid.UUID | None,
) -> tuple[RecapShareLink, str]:
    if recap.current_revision_id is None:
        raise ShareLinkNotAvailableError("no revision to share")
    revision = await session.get(RecapRevision, recap.current_revision_id)
    if revision is None or revision.status != RecapStatus.APPROVED.value:
        raise ShareLinkNotAvailableError("recap must be approved before it can be shared")
    ttl_hours = min(max(ttl_hours, 1), MAX_SHARE_LINK_TTL_HOURS)

    token = secrets.token_urlsafe(32)
    link = RecapShareLink(
        conversation_id=conversation_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        created_by_user_id=created_by_user_id,
    )
    session.add(link)
    await session.flush()
    return link, token


async def list_share_links(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> list[RecapShareLink]:
    result = await session.execute(
        select(RecapShareLink)
        .where(RecapShareLink.conversation_id == conversation_id)
        .order_by(RecapShareLink.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_share_link(session: AsyncSession, link: RecapShareLink) -> None:
    link.revoked_at = datetime.now(UTC)
    await session.flush()


async def get_valid_share_link(session: AsyncSession, *, token: str) -> RecapShareLink | None:
    """Returns the link only if it is neither expired nor revoked --
    every other distinction (doesn't exist / expired / revoked) is
    deliberately collapsed into the same "not available" outcome by the
    caller, matching this project's established never-distinguish-404-
    reasons posture for anything reachable without normal authorization."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await session.execute(
        select(RecapShareLink).where(RecapShareLink.token_hash == token_hash)
    )
    link = result.scalar_one_or_none()
    if link is None:
        return None
    if link.revoked_at is not None:
        return None
    # SQLite (the test suite's DB, see tests/conversations/conftest.py's
    # app_env fixture) round-trips DateTime(timezone=True) values as
    # naive -- Postgres returns them tz-aware. Every datetime this table
    # ever stores was written as `datetime.now(UTC) + ...`, so a naive
    # value read back is always really UTC; normalizing here keeps this
    # comparison correct under both dialects instead of raising
    # "can't compare offset-naive and offset-aware datetimes" on SQLite.
    expires_at = link.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return link


async def record_share_link_access(session: AsyncSession, link: RecapShareLink) -> None:
    link.access_count += 1
    link.last_accessed_at = datetime.now(UTC)
    await session.flush()
