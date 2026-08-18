"""REST endpoints for the conversation-capture domain: conversations,
media, participants, markers, notes. Every route enforces
Permission + Organization Membership + Conversation's Organization via
`app.conversations.authz`; nothing here trusts a bare UUID path parameter.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import (
    assert_organization_member_or_admin,
    authorize_conversation_access,
)
from app.conversations.models import (
    ConversationMarker,
    ConversationNote,
    ConversationParticipant,
    ConversationStatus,
)
from app.conversations.schemas import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MarkerCreateRequest,
    MarkerResponse,
    MarkerUpdateRequest,
    MediaAssetResponse,
    NoteCreateRequest,
    NoteResponse,
    NoteUpdateRequest,
    ParticipantCreateRequest,
    ParticipantResponse,
    ParticipantUpdateRequest,
)
from app.conversations.service import (
    add_marker,
    add_note,
    add_participant,
    apply_status_transition,
    create_conversation,
    list_conversations,
    soft_delete_conversation,
)
from app.conversations.state_machine import InvalidTransitionError
from app.core.storage import get_storage_provider
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.media.models import MediaAsset, MediaKind, MediaSourceType
from app.media.service import ingest_media, spool_upload
from app.media.validation import (
    UploadValidationError,
    content_disposition_filename,
    sanitize_display_filename,
)
from app.platform.config import get_settings
from app.platform.db.session import get_session
from app.providers.storage import StorageProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _upload_chunks(file: UploadFile, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        yield chunk


# -- Conversations ----------------------------------------------------------


@router.get("", response_model=ConversationListResponse)
async def list_conversations_endpoint(
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationListResponse:
    from app.identity.rbac import get_user_permissions
    from app.organizations.models import OrganizationMembership

    permissions = await get_user_permissions(db, user.id)
    if "conversation:read" not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    org_ids: set[uuid.UUID] | None
    if "system:admin" in permissions:
        org_ids = None
    else:
        result = await db.execute(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user.id
            )
        )
        org_ids = {row[0] for row in result.all()}

    items, total = await list_conversations(
        db,
        organization_ids=org_ids,
        status_filter=status_filter,
        type_filter=type_filter,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation_endpoint(
    payload: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ConversationResponse:
    from app.identity.rbac import get_user_permissions

    permissions = await get_user_permissions(db, user.id)
    if "conversation:create" not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    await assert_organization_member_or_admin(
        db, user=user, organization_id=payload.organization_id
    )

    conversation = await create_conversation(
        db,
        organization_id=payload.organization_id,
        created_by_user_id=user.id,
        title=payload.title,
        description=payload.description,
        conversation_type=payload.conversation_type,
        external_reference=payload.external_reference,
        external_reference_type=payload.external_reference_type,
        privacy_mode=payload.privacy_mode,
    )
    await record_event(
        db,
        event_type="conversation.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id)},
    )
    await db.commit()
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:read"
    )
    return ConversationResponse.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_endpoint(
    conversation_id: uuid.UUID,
    payload: ConversationUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ConversationResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:update"
    )
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(conversation, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="conversation.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id), "fields": list(changed.keys())},
    )
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
    _csrf: None = Depends(require_csrf),
) -> None:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:delete"
    )
    await soft_delete_conversation(db, conversation, storage=storage)
    await record_event(
        db,
        event_type="conversation.deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id)},
    )
    await db.commit()


# -- Recording finalize / media upload --------------------------------------


@router.post(
    "/{conversation_id}/recordings",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def finalize_recording_endpoint(
    conversation_id: uuid.UUID,
    request: Request,
    idempotency_key: str = Query(...),
    original_filename: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
    _csrf: None = Depends(require_csrf),
) -> MediaAssetResponse:
    """Finalizes a browser recording: the frontend accumulates
    `MediaRecorder` chunks client-side and streams the assembled blob here
    as the request body once recording stops (see
    docs/architecture/adr/0012-chunked-upload-decision.md for why Phase 2
    does not implement server-side chunk-by-chunk ingestion). Idempotent on
    `idempotency_key`: a retried finalize (e.g. after a flaky network
    response) returns the already-created MediaAsset rather than creating
    a duplicate."""
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:record"
    )

    from datetime import UTC, datetime, timedelta

    from app.media.models import RecordingUpload, RecordingUploadStatus

    existing_upload = await db.execute(
        select(RecordingUpload).where(
            RecordingUpload.conversation_id == conversation.id,
            RecordingUpload.idempotency_key == idempotency_key,
        )
    )
    upload_session = existing_upload.scalar_one_or_none()
    if (
        upload_session is not None
        and upload_session.status == RecordingUploadStatus.COMPLETED.value
    ):
        if upload_session.result_media_id is not None:
            result = await db.execute(
                select(MediaAsset).where(MediaAsset.id == upload_session.result_media_id)
            )
            already = result.scalar_one_or_none()
            if already is not None:
                return MediaAssetResponse.model_validate(already)

    if upload_session is None:
        upload_session = RecordingUpload(
            conversation_id=conversation.id,
            created_by_user_id=user.id,
            status=RecordingUploadStatus.IN_PROGRESS.value,
            idempotency_key=idempotency_key,
            expires_at=datetime.now(UTC) + timedelta(hours=6),
        )
        db.add(upload_session)
        await db.flush()

    await record_event(
        db,
        event_type="conversation.recording_started",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id)},
    )

    settings = get_settings()
    try:
        spooled = await spool_upload(
            request.stream(),
            temp_dir=settings.upload_temp_dir,
            max_size_bytes=settings.max_upload_size_bytes,
        )
        media = await ingest_media(
            db,
            spooled=spooled,
            conversation_id=conversation.id,
            organization_id=conversation.organization_id,
            kind=MediaKind.SOURCE_AUDIO,
            source_type=MediaSourceType.BROWSER_RECORDING,
            original_filename=sanitize_display_filename(original_filename),
            created_by_user_id=user.id,
            storage=storage,
        )
    except UploadValidationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.reason
        ) from exc

    try:
        apply_status_transition(conversation, ConversationStatus.UPLOADED)
    except InvalidTransitionError:
        pass  # already uploaded/ready via a prior finalize race; media row above is idempotent
    upload_session.status = RecordingUploadStatus.COMPLETED.value
    upload_session.result_media_id = media.id
    upload_session.received_bytes = spooled.size_bytes
    await record_event(
        db,
        event_type="conversation.recording_completed",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id), "media_id": str(media.id)},
    )
    await record_event(
        db,
        event_type="media.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"media_id": str(media.id), "conversation_id": str(conversation.id)},
    )
    await db.commit()
    return MediaAssetResponse.model_validate(media)


@router.post(
    "/{conversation_id}/media",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media_endpoint(
    conversation_id: uuid.UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
    _csrf: None = Depends(require_csrf),
) -> MediaAssetResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:upload"
    )
    settings = get_settings()
    try:
        spooled = await spool_upload(
            _upload_chunks(file),
            temp_dir=settings.upload_temp_dir,
            max_size_bytes=settings.max_upload_size_bytes,
        )
        media = await ingest_media(
            db,
            spooled=spooled,
            conversation_id=conversation.id,
            organization_id=conversation.organization_id,
            kind=MediaKind.SOURCE_AUDIO,
            source_type=MediaSourceType.FILE_UPLOAD,
            original_filename=sanitize_display_filename(file.filename),
            created_by_user_id=user.id,
            storage=storage,
        )
    except UploadValidationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.reason
        ) from exc

    try:
        apply_status_transition(conversation, ConversationStatus.UPLOADED)
    except InvalidTransitionError:
        pass
    await record_event(
        db,
        event_type="conversation.uploaded",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation.id), "media_id": str(media.id)},
    )
    await record_event(
        db,
        event_type="media.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"media_id": str(media.id), "conversation_id": str(conversation.id)},
    )
    await db.commit()
    return MediaAssetResponse.model_validate(media)


@router.get("/{conversation_id}/media", response_model=list[MediaAssetResponse])
async def list_media_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[MediaAssetResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="media:read"
    )
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.conversation_id == conversation_id, MediaAsset.deleted_at.is_(None)
        )
    )
    return [MediaAssetResponse.model_validate(m) for m in result.scalars().all()]


async def _get_media_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, media_id: uuid.UUID
) -> MediaAsset:
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == media_id,
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media not found")
    return media


@router.get("/{conversation_id}/media/{media_id}", response_model=MediaAssetResponse)
async def get_media_endpoint(
    conversation_id: uuid.UUID,
    media_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> MediaAssetResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="media:read"
    )
    media = await _get_media_or_404(db, conversation_id, media_id)
    return MediaAssetResponse.model_validate(media)


@router.get("/{conversation_id}/media/{media_id}/content")
async def get_media_content_endpoint(
    conversation_id: uuid.UUID,
    media_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
) -> FileResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="media:read"
    )
    media = await _get_media_or_404(db, conversation_id, media_id)
    path = await storage.open_path(media.storage_key)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media content missing")

    await record_event(
        db,
        event_type="media.downloaded",
        user_id=user.id,
        username=user.username,
        event_metadata={"media_id": str(media.id)},
    )
    await db.commit()

    filename = content_disposition_filename(media.original_filename)
    return FileResponse(path=path, media_type=media.content_type, filename=filename)


@router.delete("/{conversation_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_endpoint(
    conversation_id: uuid.UUID,
    media_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="media:delete"
    )
    media = await _get_media_or_404(db, conversation_id, media_id)
    from datetime import UTC, datetime

    await storage.delete(media.storage_key)
    media.deleted_at = datetime.now(UTC)
    await record_event(
        db,
        event_type="media.deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"media_id": str(media.id), "conversation_id": str(conversation_id)},
    )
    await db.commit()


# -- Participants -------------------------------------------------------


@router.get("/{conversation_id}/participants", response_model=list[ParticipantResponse])
async def list_participants_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ParticipantResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:read"
    )
    result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id
        )
    )
    return [ParticipantResponse.model_validate(p) for p in result.scalars().all()]


@router.post(
    "/{conversation_id}/participants",
    response_model=ParticipantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_participant_endpoint(
    conversation_id: uuid.UUID,
    payload: ParticipantCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ParticipantResponse:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-participants",
    )
    participant = await add_participant(
        db,
        conversation_id=conversation_id,
        display_name=payload.display_name,
        participant_type=payload.participant_type,
        external_reference=payload.external_reference,
        notes=payload.notes,
    )
    await record_event(
        db,
        event_type="conversation.participant_added",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "conversation_id": str(conversation_id),
            "participant_id": str(participant.id),
        },
    )
    await db.commit()
    return ParticipantResponse.model_validate(participant)


async def _get_participant_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, participant_id: uuid.UUID
) -> ConversationParticipant:
    result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.id == participant_id,
            ConversationParticipant.conversation_id == conversation_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="participant not found")
    return participant


@router.patch(
    "/{conversation_id}/participants/{participant_id}", response_model=ParticipantResponse
)
async def update_participant_endpoint(
    conversation_id: uuid.UUID,
    participant_id: uuid.UUID,
    payload: ParticipantUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ParticipantResponse:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-participants",
    )
    participant = await _get_participant_or_404(db, conversation_id, participant_id)
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(participant, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="conversation.participant_updated",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "conversation_id": str(conversation_id),
            "participant_id": str(participant_id),
        },
    )
    await db.commit()
    await db.refresh(participant)
    return ParticipantResponse.model_validate(participant)


@router.delete(
    "/{conversation_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_participant_endpoint(
    conversation_id: uuid.UUID,
    participant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-participants",
    )
    participant = await _get_participant_or_404(db, conversation_id, participant_id)
    await db.delete(participant)
    await record_event(
        db,
        event_type="conversation.participant_removed",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "conversation_id": str(conversation_id),
            "participant_id": str(participant_id),
        },
    )
    await db.commit()


# -- Markers ------------------------------------------------------------


@router.get("/{conversation_id}/markers", response_model=list[MarkerResponse])
async def list_markers_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[MarkerResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:read"
    )
    result = await db.execute(
        select(ConversationMarker)
        .where(ConversationMarker.conversation_id == conversation_id)
        .order_by(ConversationMarker.timestamp_ms.asc())
    )
    return [MarkerResponse.model_validate(m) for m in result.scalars().all()]


@router.post(
    "/{conversation_id}/markers", response_model=MarkerResponse, status_code=status.HTTP_201_CREATED
)
async def create_marker_endpoint(
    conversation_id: uuid.UUID,
    payload: MarkerCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> MarkerResponse:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-markers",
    )
    marker = await add_marker(
        db,
        conversation_id=conversation_id,
        created_by_user_id=user.id,
        timestamp_ms=payload.timestamp_ms,
        label=payload.label,
        note=payload.note,
    )
    await record_event(
        db,
        event_type="conversation.marker_created",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "marker_id": str(marker.id)},
    )
    await db.commit()
    return MarkerResponse.model_validate(marker)


async def _get_marker_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, marker_id: uuid.UUID
) -> ConversationMarker:
    result = await db.execute(
        select(ConversationMarker).where(
            ConversationMarker.id == marker_id,
            ConversationMarker.conversation_id == conversation_id,
        )
    )
    marker = result.scalar_one_or_none()
    if marker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="marker not found")
    return marker


@router.patch("/{conversation_id}/markers/{marker_id}", response_model=MarkerResponse)
async def update_marker_endpoint(
    conversation_id: uuid.UUID,
    marker_id: uuid.UUID,
    payload: MarkerUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> MarkerResponse:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-markers",
    )
    marker = await _get_marker_or_404(db, conversation_id, marker_id)
    changed = payload.model_dump(exclude_unset=True)
    if (
        "timestamp_ms" in changed
        and changed["timestamp_ms"] is not None
        and changed["timestamp_ms"] < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid timestamp"
        )
    for field, value in changed.items():
        setattr(marker, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="conversation.marker_updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "marker_id": str(marker_id)},
    )
    await db.commit()
    await db.refresh(marker)
    return MarkerResponse.model_validate(marker)


@router.delete("/{conversation_id}/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_marker_endpoint(
    conversation_id: uuid.UUID,
    marker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db,
        user=user,
        conversation_id=conversation_id,
        permission_code="conversation:manage-markers",
    )
    marker = await _get_marker_or_404(db, conversation_id, marker_id)
    await db.delete(marker)
    await record_event(
        db,
        event_type="conversation.marker_deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "marker_id": str(marker_id)},
    )
    await db.commit()


# -- Notes ----------------------------------------------------------------


@router.get("/{conversation_id}/notes", response_model=list[NoteResponse])
async def list_notes_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[NoteResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:read"
    )
    result = await db.execute(
        select(ConversationNote)
        .where(ConversationNote.conversation_id == conversation_id)
        .order_by(ConversationNote.created_at.asc())
    )
    return [NoteResponse.model_validate(n) for n in result.scalars().all()]


@router.post(
    "/{conversation_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED
)
async def create_note_endpoint(
    conversation_id: uuid.UUID,
    payload: NoteCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> NoteResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:manage-notes"
    )
    note = await add_note(
        db,
        conversation_id=conversation_id,
        created_by_user_id=user.id,
        content=payload.content,
        timestamp_ms=payload.timestamp_ms,
    )
    await record_event(
        db,
        event_type="conversation.note_created",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "note_id": str(note.id)},
    )
    await db.commit()
    return NoteResponse.model_validate(note)


async def _get_note_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, note_id: uuid.UUID
) -> ConversationNote:
    result = await db.execute(
        select(ConversationNote).where(
            ConversationNote.id == note_id, ConversationNote.conversation_id == conversation_id
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    return note


@router.patch("/{conversation_id}/notes/{note_id}", response_model=NoteResponse)
async def update_note_endpoint(
    conversation_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> NoteResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:manage-notes"
    )
    note = await _get_note_or_404(db, conversation_id, note_id)
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(note, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="conversation.note_updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "note_id": str(note_id)},
    )
    await db.commit()
    await db.refresh(note)
    return NoteResponse.model_validate(note)


@router.delete("/{conversation_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_endpoint(
    conversation_id: uuid.UUID,
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:manage-notes"
    )
    note = await _get_note_or_404(db, conversation_id, note_id)
    await db.delete(note)
    await record_event(
        db,
        event_type="conversation.note_deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"conversation_id": str(conversation_id), "note_id": str(note_id)},
    )
    await db.commit()
