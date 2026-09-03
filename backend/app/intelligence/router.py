"""REST endpoints for fact extraction + facts/evidence/review-issue
reads. Every route enforces Permission + Organization Membership +
Conversation's Organization via `app.conversations.authz`, matching the
Phase 2/3 pattern exactly — a fact/evidence/review-issue is never
reachable except through its (authorized) conversation, and is exactly as
sensitive as the transcript it derives from.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.authz import authorize_conversation_access
from app.evidence.models import FactEvidence
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.intelligence.api_schemas import (
    ExtractedFactResponse,
    ExtractRequest,
    FactEvidenceResponse,
    ReviewIssueResponse,
)
from app.intelligence.models import ExtractedFact
from app.media.models import MediaAsset, MediaKind
from app.platform.config import get_settings
from app.platform.db.session import get_session
from app.platform.valkey.backends import QueueBackend
from app.processing.orchestrator import start_extraction
from app.processing.service import count_active_jobs_for_conversation
from app.review.models import ReviewIssue
from app.transcription.models import TranscriptSegment

router = APIRouter(prefix="/conversations", tags=["intelligence"])


async def _get_queue_backend() -> QueueBackend:
    from app.core.ai_providers import get_queue_backend

    return get_queue_backend()


async def _get_source_media_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> MediaAsset:
    result = await db.execute(
        select(MediaAsset)
        .where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.SOURCE_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc())
    )
    media = result.scalars().first()
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no source audio for this conversation"
        )
    return media


@router.post(
    "/{conversation_id}/process/extract",
    response_model=list[ExtractedFactResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_facts_endpoint(
    conversation_id: uuid.UUID,
    body: ExtractRequest,  # noqa: ARG001 - reserved for future options, always empty today
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    queue: QueueBackend = Depends(_get_queue_backend),
    _csrf: None = Depends(require_csrf),
) -> list[ExtractedFactResponse]:
    """Explicit user action to start extraction — never triggered
    automatically once a transcript is READY (spec: "explicit trigger,
    not automatic"). Returns 202 immediately; the job runs async (see
    app.processing.orchestrator.execute_extract) — poll
    `GET /conversations/{id}/facts` or `/processing` for results."""
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="fact:extract"
    )
    source_media = await _get_source_media_or_404(db, conversation_id)

    settings = get_settings()
    active_count = await count_active_jobs_for_conversation(db, conversation_id=conversation_id)
    if active_count >= settings.max_active_processing_jobs_per_conversation:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many active processing jobs for this conversation",
        )

    try:
        await start_extraction(
            db, queue, conversation=conversation, source_media=source_media, requested_by=user
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return []


@router.get("/{conversation_id}/facts", response_model=list[ExtractedFactResponse])
async def list_facts_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ExtractedFactResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="fact:read"
    )
    result = await db.execute(
        select(ExtractedFact)
        .where(ExtractedFact.conversation_id == conversation_id)
        .order_by(ExtractedFact.created_at.asc())
    )
    return [ExtractedFactResponse.model_validate(f) for f in result.scalars().all()]


async def _get_fact_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, fact_id: uuid.UUID
) -> ExtractedFact:
    result = await db.execute(
        select(ExtractedFact).where(
            ExtractedFact.id == fact_id, ExtractedFact.conversation_id == conversation_id
        )
    )
    fact = result.scalar_one_or_none()
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fact not found")
    return fact


@router.get("/{conversation_id}/facts/{fact_id}", response_model=ExtractedFactResponse)
async def get_fact_endpoint(
    conversation_id: uuid.UUID,
    fact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ExtractedFactResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="fact:read"
    )
    fact = await _get_fact_or_404(db, conversation_id, fact_id)
    return ExtractedFactResponse.model_validate(fact)


@router.get(
    "/{conversation_id}/facts/{fact_id}/evidence", response_model=list[FactEvidenceResponse]
)
async def get_fact_evidence_endpoint(
    conversation_id: uuid.UUID,
    fact_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[FactEvidenceResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="evidence:read"
    )
    await _get_fact_or_404(db, conversation_id, fact_id)  # 404s before leaking evidence rows

    result = await db.execute(
        select(FactEvidence, TranscriptSegment)
        .join(TranscriptSegment, FactEvidence.transcript_segment_id == TranscriptSegment.id)
        .where(FactEvidence.fact_id == fact_id)
        .order_by(TranscriptSegment.sequence.asc())
    )
    responses = []
    for evidence, segment in result.all():
        resp = FactEvidenceResponse.model_validate(evidence)
        resp.segment_sequence = segment.sequence
        resp.segment_start_ms = segment.start_ms
        resp.segment_end_ms = segment.end_ms
        resp.segment_text = segment.corrected_text or segment.original_text
        responses.append(resp)
    return responses


@router.get("/{conversation_id}/review-issues", response_model=list[ReviewIssueResponse])
async def list_review_issues_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ReviewIssueResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="review-issue:read"
    )
    result = await db.execute(
        select(ReviewIssue)
        .where(ReviewIssue.conversation_id == conversation_id)
        .order_by(ReviewIssue.created_at.asc())
    )
    return [ReviewIssueResponse.model_validate(i) for i in result.scalars().all()]
