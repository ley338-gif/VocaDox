"""REST endpoints for Recap generation, viewing, approval, and export.
Every route enforces Permission + Organization Membership via
`app.conversations.authz`, identical to the Document domain — a Recap is
exactly as sensitive as the Document it's derived from.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import authorize_conversation_access
from app.core.ai_providers import get_llm_provider
from app.identity.deps import get_current_user, require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.providers.llm import LLMProvider
from app.recap.api_schemas import RecapResponse, RecapRevisionResponse
from app.recap.models import Recap, RecapRevision
from app.recap.service import (
    RecapApprovalError,
    RecapNotComposableError,
    approve_recap,
    generate_recap,
)

router = APIRouter(prefix="/conversations", tags=["recap"])

_require_generate = require_permission("recap:generate")
_require_approve = require_permission("recap:approve")


async def _get_recap_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> Recap:
    result = await db.execute(select(Recap).where(Recap.conversation_id == conversation_id))
    recap = result.scalar_one_or_none()
    if recap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no recap generated yet")
    return recap


async def _recap_response(db: AsyncSession, recap: Recap) -> RecapResponse:
    revision = None
    if recap.current_revision_id is not None:
        revision = await db.get(RecapRevision, recap.current_revision_id)
    resp = RecapResponse.model_validate(recap)
    resp.current_revision = (
        RecapRevisionResponse.model_validate(revision) if revision is not None else None
    )
    return resp


@router.get("/{conversation_id}/recap", response_model=RecapResponse)
async def get_recap_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> RecapResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:read"
    )
    recap = await _get_recap_or_404(db, conversation_id)
    return await _recap_response(db, recap)


@router.post("/{conversation_id}/recap/generate", response_model=RecapResponse)
async def generate_recap_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(_require_generate),
    db: AsyncSession = Depends(get_session),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    _csrf: None = Depends(require_csrf),
) -> RecapResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:generate"
    )
    try:
        recap = await generate_recap(
            db, conversation_id=conversation_id, provider=llm_provider, requested_by=user
        )
    except RecapNotComposableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await record_event(
        db,
        event_type="recap.generated",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "recap_id": str(recap.id)},
    )
    await db.commit()
    await db.refresh(recap)
    return await _recap_response(db, recap)


@router.post("/{conversation_id}/recap/approve", response_model=RecapResponse)
async def approve_recap_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(_require_approve),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> RecapResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:approve"
    )
    recap = await _get_recap_or_404(db, conversation_id)
    try:
        recap = await approve_recap(db, recap=recap, approved_by=user)
    except RecapApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await record_event(
        db,
        event_type="recap.approved",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "recap_id": str(recap.id)},
    )
    await db.commit()
    await db.refresh(recap)
    return await _recap_response(db, recap)


@router.get("/{conversation_id}/recap/export")
async def export_recap_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Plain text export — the recap is meant to be copied into an email
    or printed, matching the Document export's minimalism (PDF/DOCX
    deliberately deferred, same rationale as app.documents.router)."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:read"
    )
    recap = await _get_recap_or_404(db, conversation_id)
    if recap.current_revision_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no revision to export")
    revision = await db.get(RecapRevision, recap.current_revision_id)
    assert revision is not None
    if revision.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="recap must be approved before it can be exported",
        )
    content = revision.content

    await record_event(
        db,
        event_type="recap.exported",
        user_id=user.id,
        event_metadata={"conversation_id": str(conversation_id), "recap_id": str(recap.id)},
    )
    await db.commit()
    return Response(content=content, media_type="text/plain")
