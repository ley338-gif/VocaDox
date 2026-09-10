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
from app.documents.export_formats import ExportSection, render_docx, render_pdf
from app.identity.deps import get_current_user, require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.providers.llm import LLMProvider
from app.recap.api_schemas import (
    CreateShareLinkRequest,
    RecapResponse,
    RecapRevisionResponse,
    ShareLinkCreatedResponse,
    ShareLinkResponse,
)
from app.recap.models import Recap, RecapRevision, RecapShareLink
from app.recap.service import (
    RecapApprovalError,
    RecapNotComposableError,
    ShareLinkNotAvailableError,
    approve_recap,
    create_share_link,
    generate_recap,
    list_share_links,
    revoke_share_link,
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
    format: str = "text",  # noqa: A002 - matches the query param name intentionally
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Plain text / DOCX / PDF export — the recap is meant to be copied
    into an email, printed, or attached as a real file (post-GA P0-2)."""
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
    revision_number = revision.revision_number

    await record_event(
        db,
        event_type="recap.exported",
        user_id=user.id,
        event_metadata={
            "conversation_id": str(conversation_id),
            "recap_id": str(recap.id),
            "format": format,
        },
    )
    await db.commit()

    meta_lines = [f"Status: approved (revision {revision_number})"]
    if format in ("docx", "pdf"):
        sections = [ExportSection(heading=None, lines=content.split("\n\n"))]
        filename = f"recap-{recap.id}-r{revision_number}.{format}"
        if format == "docx":
            render_content = render_docx(title="Recap", meta_lines=meta_lines, sections=sections)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            render_content = render_pdf(title="Recap", meta_lines=meta_lines, sections=sections)
            media_type = "application/pdf"
        return Response(
            content=render_content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Plain-text stays byte-identical to its pre-P0-2 shape (existing
    # callers/tests assert `content` verbatim) -- the new DOCX/PDF formats
    # are where the status/revision-number visibility requirement lands.
    return Response(content=content, media_type="text/plain")


# -- Share links (post-GA P3-2) ------------------------------------------


@router.post(
    "/{conversation_id}/recap/share-links",
    response_model=ShareLinkCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_link_endpoint(
    conversation_id: uuid.UUID,
    body: CreateShareLinkRequest,
    user: User = Depends(_require_approve),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ShareLinkCreatedResponse:
    """Requires `recap:approve` -- the same trust level already required
    to approve the recap in the first place; sharing it externally is at
    least as consequential as approving it."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:approve"
    )
    recap = await _get_recap_or_404(db, conversation_id)
    try:
        link, token = await create_share_link(
            db,
            conversation_id=conversation_id,
            recap=recap,
            ttl_hours=body.ttl_hours,
            created_by_user_id=user.id,
        )
    except ShareLinkNotAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await record_event(
        db,
        event_type="recap.share_link_created",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "conversation_id": str(conversation_id),
            "recap_id": str(recap.id),
            "share_link_id": str(link.id),
            "expires_at": link.expires_at.isoformat(),
        },
    )
    await db.commit()
    await db.refresh(link)
    return ShareLinkCreatedResponse(
        **ShareLinkResponse.model_validate(link).model_dump(), token=token
    )


@router.get("/{conversation_id}/recap/share-links", response_model=list[ShareLinkResponse])
async def list_share_links_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(_require_approve),
    db: AsyncSession = Depends(get_session),
) -> list[ShareLinkResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:approve"
    )
    links = await list_share_links(db, conversation_id=conversation_id)
    return [ShareLinkResponse.model_validate(link) for link in links]


async def _get_share_link_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, link_id: uuid.UUID
) -> RecapShareLink:
    result = await db.execute(
        select(RecapShareLink).where(
            RecapShareLink.id == link_id, RecapShareLink.conversation_id == conversation_id
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share link not found")
    return link


@router.delete(
    "/{conversation_id}/recap/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_share_link_endpoint(
    conversation_id: uuid.UUID,
    link_id: uuid.UUID,
    user: User = Depends(_require_approve),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="recap:approve"
    )
    link = await _get_share_link_or_404(db, conversation_id, link_id)
    await revoke_share_link(db, link)
    await record_event(
        db,
        event_type="recap.share_link_revoked",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "share_link_id": str(link_id)},
    )
    await db.commit()
