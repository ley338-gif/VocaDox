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

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentRevision
from app.identity.models import User
from app.providers.llm import LLMProvider
from app.recap.models import Recap, RecapRevision, RecapStatus
from app.recap.prompts import SYSTEM_PROMPT, build_prompt
from app.transcription.models import Transcript


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


async def approve_recap(
    session: AsyncSession, *, recap: Recap, approved_by: User
) -> Recap:
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
