"""REST endpoints for document composition, revisions, the Review Wizard
(review-issue resolution), approval, and export. Every route enforces
Permission + Organization Membership + Conversation's Organization via
`app.conversations.authz`, identical to every Phase 2/3/4 resource — a
document is exactly as sensitive as the facts/transcript it derives from.
"""

from __future__ import annotations

import json as _json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.authz import authorize_conversation_access
from app.documents.api_schemas import (
    ApprovalBlockedResponse,
    ComposeRequest,
    DocumentResponse,
    DocumentRevisionResponse,
    ResolveReviewIssueRequest,
)
from app.documents.models import Document, DocumentRevision
from app.documents.service import (
    ApprovalBlockedError,
    DocumentNotComposableError,
    approve_document,
    compose_document,
    resolve_review_issue,
)
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.intelligence.api_schemas import ReviewIssueResponse
from app.intelligence.models import ExtractedFact
from app.platform.db.session import get_session
from app.review.models import ReviewIssue, ReviewIssueResolution

router = APIRouter(prefix="/conversations", tags=["documents"])


async def _get_document_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> Document:
    result = await db.execute(select(Document).where(Document.conversation_id == conversation_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no document composed yet"
        )
    return document


async def _document_response(db: AsyncSession, document: Document) -> DocumentResponse:
    revision = None
    if document.current_revision_id is not None:
        revision = await db.get(DocumentRevision, document.current_revision_id)
    resp = DocumentResponse.model_validate(document)
    resp.current_revision = (
        DocumentRevisionResponse.model_validate(revision) if revision is not None else None
    )
    return resp


@router.get("/{conversation_id}/document", response_model=DocumentResponse)
async def get_document_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="document:read"
    )
    document = await _get_document_or_404(db, conversation_id)
    return await _document_response(db, document)


@router.post("/{conversation_id}/document/compose", response_model=DocumentResponse)
async def compose_document_endpoint(
    conversation_id: uuid.UUID,
    body: ComposeRequest,  # noqa: ARG001 - reserved for future options, always empty today
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> DocumentResponse:
    """Explicit user action (spec: "explicit trigger, not automatic") — see
    app.documents.service's module docstring / ADR-0027 for why this runs
    synchronously rather than via the ProcessingJob/worker queue used by
    every provider-backed stage."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="document:edit"
    )
    try:
        document = await compose_document(db, conversation_id=conversation_id, requested_by=user)
    except DocumentNotComposableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(document)
    return await _document_response(db, document)


@router.get(
    "/{conversation_id}/document/revisions", response_model=list[DocumentRevisionResponse]
)
async def list_revisions_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[DocumentRevisionResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="document:read"
    )
    document = await _get_document_or_404(db, conversation_id)
    result = await db.execute(
        select(DocumentRevision)
        .where(DocumentRevision.document_id == document.id)
        .order_by(DocumentRevision.revision_number.asc())
    )
    return [DocumentRevisionResponse.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/{conversation_id}/document/approve",
    response_model=DocumentResponse,
    responses={409: {"model": ApprovalBlockedResponse}},
)
async def approve_document_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> DocumentResponse:
    """**The AI never calls this.** Requires `document:approve` (only
    granted to System Admin/Manager/Reviewer roles by default — see
    app.identity.seed) and no unresolved HIGH/CRITICAL review issue (spec
    §27)."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="document:approve"
    )
    document = await _get_document_or_404(db, conversation_id)
    try:
        document = await approve_document(
            db, document=document, conversation_id=conversation_id, approved_by=user
        )
    except ApprovalBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": str(exc),
                "blocking_issue_ids": exc.blocking_issue_ids,
            },
        ) from exc
    except DocumentNotComposableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(document)
    return await _document_response(db, document)


@router.get("/{conversation_id}/document/export")
async def export_document_endpoint(
    conversation_id: uuid.UUID,
    format: str = "text",  # noqa: A002 - matches the query param name intentionally
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Plain text / JSON export of the current revision (spec: "at minimum
    plain text and/or a simple structured format"). See
    docs/architecture/adr's compliance notes / PHASE_5_VALIDATION_REPORT.md
    for why PDF/DOCX generation is deliberately deferred rather than adding
    an unresearched new dependency under time pressure."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="document:read"
    )
    document = await _get_document_or_404(db, conversation_id)
    if document.current_revision_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no revision to export")
    revision = await db.get(DocumentRevision, document.current_revision_id)
    assert revision is not None
    # Captured before commit — a post-commit attribute access on an
    # expired ORM object would trigger an implicit lazy-load, which is not
    # safe to await from a sync response-building branch below.
    revision_number = revision.revision_number
    revision_status = revision.status
    revision_content = revision.structured_content
    revision_text = revision.rendered_text
    document_id = document.id

    from app.audit.service import record_event

    await record_event(
        db,
        event_type="document.exported",
        user_id=user.id,
        event_metadata={
            "conversation_id": str(conversation_id),
            "document_id": str(document_id),
            "revision_id": str(revision.id),
            "format": format,
        },
    )
    await db.commit()

    if format == "json":
        payload = {
            "document_id": str(document_id),
            "conversation_id": str(conversation_id),
            "revision_number": revision_number,
            "status": revision_status,
            "sections": revision_content,
        }
        return Response(content=_json.dumps(payload, indent=2), media_type="application/json")

    header = f"Status: {revision_status} (revision {revision_number})\n\n"
    return Response(content=header + revision_text, media_type="text/plain")


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


@router.patch("/{conversation_id}/review-issues/{issue_id}", response_model=ReviewIssueResponse)
async def resolve_review_issue_endpoint(
    conversation_id: uuid.UUID,
    issue_id: uuid.UUID,
    body: ResolveReviewIssueRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ReviewIssueResponse:
    """One Review Wizard decision (spec §28: Confirm/Correct/Remove) on one
    flagged item. `body.fact_id` must be one of the issue's
    `related_fact_ids` — resolving a multi-fact (contradiction) issue
    targets exactly the fact the reviewer is acting on; the issue closes
    once this one decision is recorded (matching the wizard's "one
    decision per flagged item" flow), the other fact is left untouched."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="review-issue:resolve"
    )
    result = await db.execute(
        select(ReviewIssue).where(
            ReviewIssue.id == issue_id, ReviewIssue.conversation_id == conversation_id
        )
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review issue not found")
    if issue.status == "resolved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="issue already resolved")
    if str(body.fact_id) not in issue.related_fact_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fact_id is not related to this review issue",
        )
    fact = await _get_fact_or_404(db, conversation_id, body.fact_id)

    try:
        await resolve_review_issue(
            db,
            issue=issue,
            fact=fact,
            action=_map_action(body.action),
            corrected_value=body.corrected_value,
            resolved_by=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(issue)
    return ReviewIssueResponse.model_validate(issue)


def _map_action(action: str) -> ReviewIssueResolution:
    return {
        "confirm": ReviewIssueResolution.CONFIRMED,
        "correct": ReviewIssueResolution.CORRECTED,
        "remove": ReviewIssueResolution.REMOVED,
    }[action]
