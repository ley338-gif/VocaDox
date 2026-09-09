"""REST endpoints for the Protokoll surface (Post-GA) — mirrors
`app.documents.router`'s conventions (auth/permission dependency
injection, `_get_or_404`-style helpers, manual nested-response
construction) and `app.intelligence.router`'s async-job trigger pattern
(`/process/extract` -> `/protocol/generate`) exactly, since generation is
LLM-driven like extraction, not deterministic like composition.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.authz import authorize_conversation_access
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.media.models import MediaAsset, MediaKind
from app.platform.config import get_settings
from app.platform.db.session import get_session
from app.platform.valkey.backends import QueueBackend
from app.processing.orchestrator import start_protocol_generation
from app.processing.service import count_active_jobs_for_conversation
from app.protocols.api_schemas import (
    GenerateProtocolRequest,
    ProtocolItemResponse,
    ProtocolResponse,
    ProtocolRevisionResponse,
    ProtocolRevisionSummaryResponse,
    ProtocolSectionResponse,
    ProtocolSourceResponse,
)
from app.protocols.models import (
    Protocol,
    ProtocolItem,
    ProtocolRevision,
    ProtocolSection,
    ProtocolSource,
)
from app.transcription.models import TranscriptSegment
from app.transcription.rendering import load_speaker_labels

router = APIRouter(prefix="/conversations", tags=["protocols"])


async def _get_queue_backend() -> QueueBackend:
    from app.core.ai_providers import get_queue_backend

    return get_queue_backend()


async def _get_source_media_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> MediaAsset:
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.SOURCE_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
    )
    media = result.scalars().first()
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no source audio for this conversation"
        )
    return media


async def _get_protocol_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> Protocol:
    result = await db.execute(select(Protocol).where(Protocol.conversation_id == conversation_id))
    protocol = result.scalar_one_or_none()
    if protocol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no protocol yet")
    return protocol


async def _revision_response(
    db: AsyncSession, revision: ProtocolRevision
) -> ProtocolRevisionResponse:
    resp = ProtocolRevisionResponse.model_validate(revision)
    sections_result = await db.execute(
        select(ProtocolSection)
        .where(ProtocolSection.protocol_revision_id == revision.id)
        .order_by(ProtocolSection.position.asc())
    )
    sections = list(sections_result.scalars().all())

    items_result = await db.execute(
        select(ProtocolItem)
        .join(ProtocolSection, ProtocolItem.protocol_section_id == ProtocolSection.id)
        .where(ProtocolSection.protocol_revision_id == revision.id)
        .order_by(ProtocolItem.position.asc())
    )
    items_by_section: dict[uuid.UUID, list[ProtocolItem]] = {}
    for item in items_result.scalars().all():
        items_by_section.setdefault(item.protocol_section_id, []).append(item)

    resp.sections = [
        ProtocolSectionResponse.model_validate(section).model_copy(
            update={
                "items": [
                    ProtocolItemResponse.model_validate(item)
                    for item in items_by_section.get(section.id, [])
                ]
            }
        )
        for section in sections
    ]
    return resp


async def _protocol_response(db: AsyncSession, protocol: Protocol) -> ProtocolResponse:
    resp = ProtocolResponse.model_validate(protocol)
    if protocol.current_revision_id is not None:
        revision = await db.get(ProtocolRevision, protocol.current_revision_id)
        resp.current_revision = (
            await _revision_response(db, revision) if revision is not None else None
        )
    return resp


@router.get("/{conversation_id}/protocol", response_model=ProtocolResponse)
async def get_protocol_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ProtocolResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="protocol:read"
    )
    protocol = await _get_protocol_or_404(db, conversation_id)
    return await _protocol_response(db, protocol)


@router.get(
    "/{conversation_id}/protocol/revisions", response_model=list[ProtocolRevisionSummaryResponse]
)
async def list_protocol_revisions_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ProtocolRevisionSummaryResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="protocol:read"
    )
    protocol = await _get_protocol_or_404(db, conversation_id)
    result = await db.execute(
        select(ProtocolRevision)
        .where(ProtocolRevision.protocol_id == protocol.id)
        .order_by(ProtocolRevision.revision_number.desc())
    )
    return [
        ProtocolRevisionSummaryResponse.model_validate(r) for r in result.scalars().all()
    ]


@router.post(
    "/{conversation_id}/protocol/generate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_protocol_endpoint(
    conversation_id: uuid.UUID,
    body: GenerateProtocolRequest,  # noqa: ARG001 - reserved for future options, always empty today
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    queue: QueueBackend = Depends(_get_queue_backend),
    _csrf: None = Depends(require_csrf),
) -> None:
    """Explicit user action ("Protokoll erstellen"/"Neu erstellen") —
    never triggered automatically once a transcript is READY, same
    "explicit trigger, not automatic" principle as fact extraction.
    Returns 202 immediately; the job runs async (see
    app.processing.orchestrator.execute_generate_protocol) — poll
    `GET .../protocol` or `/processing` for the result."""
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="protocol:generate"
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
        await start_protocol_generation(
            db, queue, conversation=conversation, source_media=source_media, requested_by=user
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()


async def _sources_response(
    db: AsyncSession, *, section_id: uuid.UUID | None, item_id: uuid.UUID | None
) -> list[ProtocolSourceResponse]:
    condition = (
        ProtocolSource.protocol_section_id == section_id
        if section_id is not None
        else ProtocolSource.protocol_item_id == item_id
    )
    result = await db.execute(
        select(ProtocolSource, TranscriptSegment)
        .join(TranscriptSegment, ProtocolSource.transcript_segment_id == TranscriptSegment.id)
        .where(condition)
        .order_by(TranscriptSegment.sequence.asc())
    )
    rows = result.all()
    speaker_ids = {seg.speaker_id for _, seg in rows if seg.speaker_id is not None}
    speaker_labels = await load_speaker_labels(db, speaker_ids)
    return [
        ProtocolSourceResponse(
            id=source.id,
            transcript_segment_id=segment.id,
            segment_start_ms=segment.start_ms,
            segment_end_ms=segment.end_ms,
            segment_text=segment.corrected_text or segment.original_text,
            speaker_label=speaker_labels.get(segment.speaker_id) if segment.speaker_id else None,
        )
        for source, segment in rows
    ]


async def _get_section_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, section_id: uuid.UUID
) -> ProtocolSection:
    result = await db.execute(
        select(ProtocolSection)
        .join(ProtocolRevision, ProtocolSection.protocol_revision_id == ProtocolRevision.id)
        .join(Protocol, ProtocolRevision.protocol_id == Protocol.id)
        .where(ProtocolSection.id == section_id, Protocol.conversation_id == conversation_id)
    )
    section = result.scalars().first()
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="section not found")
    return section


async def _get_item_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, item_id: uuid.UUID
) -> ProtocolItem:
    result = await db.execute(
        select(ProtocolItem)
        .join(ProtocolSection, ProtocolItem.protocol_section_id == ProtocolSection.id)
        .join(ProtocolRevision, ProtocolSection.protocol_revision_id == ProtocolRevision.id)
        .join(Protocol, ProtocolRevision.protocol_id == Protocol.id)
        .where(ProtocolItem.id == item_id, Protocol.conversation_id == conversation_id)
    )
    item = result.scalars().first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    return item


@router.get(
    "/{conversation_id}/protocol/sections/{section_id}/sources",
    response_model=list[ProtocolSourceResponse],
)
async def get_section_sources_endpoint(
    conversation_id: uuid.UUID,
    section_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ProtocolSourceResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="protocol:read"
    )
    section = await _get_section_or_404(db, conversation_id, section_id)  # 404s before leaking rows
    return await _sources_response(db, section_id=section.id, item_id=None)


@router.get(
    "/{conversation_id}/protocol/items/{item_id}/sources",
    response_model=list[ProtocolSourceResponse],
)
async def get_item_sources_endpoint(
    conversation_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ProtocolSourceResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="protocol:read"
    )
    item = await _get_item_or_404(db, conversation_id, item_id)  # 404s before leaking evidence rows
    return await _sources_response(db, section_id=None, item_id=item.id)
