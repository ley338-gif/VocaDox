"""REST endpoints for the live transcript/draft during recording (post-GA
P2-1). Same conversation-access gate as every other per-conversation
surface; ephemeral state lives only in `LiveSessionStore`, never the
database."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.authz import authorize_conversation_access
from app.core.ai_providers import get_llm_provider, get_speech_provider
from app.core.storage import get_storage_provider
from app.identity.deps import get_cache_backend, get_current_user, require_csrf
from app.identity.models import User
from app.live.schemas import LiveSessionResponse
from app.live.service import ingest_live_chunk, maybe_regenerate_live_draft
from app.live.store import LiveSessionData, LiveSessionStore
from app.platform.db.session import get_session
from app.platform.valkey.backends import CacheBackend
from app.providers.llm import LLMProvider
from app.providers.speech_to_text import SpeechToTextProvider
from app.providers.storage import StorageProvider

router = APIRouter(prefix="/conversations", tags=["live"])

# A live preview is meant for a recording in progress, not an arbitrary
# large upload -- the durable upload path (`POST .../media`) is what
# validates/spools genuinely large files. 25 MiB comfortably covers
# several minutes of opus-encoded speech.
_MAX_LIVE_CHUNK_BYTES = 25 * 1024 * 1024
# Abandoned mid-recording state (tab closed without finishing) must not
# linger forever -- 30 minutes covers any realistic single recording.
_LIVE_SESSION_TTL_SECONDS = 30 * 60


def _get_live_store(cache: CacheBackend = Depends(get_cache_backend)) -> LiveSessionStore:
    return LiveSessionStore(cache, ttl_seconds=_LIVE_SESSION_TTL_SECONDS)


def _to_response(data: LiveSessionData) -> LiveSessionResponse:
    return LiveSessionResponse(
        transcript_text=data.transcript_text,
        draft_text=data.draft_text,
        chunk_count=data.chunk_count,
        updated_at=data.updated_at,
    )


@router.post("/{conversation_id}/live/chunks", response_model=LiveSessionResponse)
async def ingest_live_chunk_endpoint(
    conversation_id: uuid.UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(get_storage_provider),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    store: LiveSessionStore = Depends(_get_live_store),
    _csrf: None = Depends(require_csrf),
) -> LiveSessionResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:record"
    )
    data = await file.read()
    if len(data) > _MAX_LIVE_CHUNK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="live chunk too large"
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty chunk")

    has_extension = bool(file.filename and "." in file.filename)
    extension = file.filename.rsplit(".", 1)[-1] if has_extension and file.filename else "webm"
    suffix = f".{extension}"
    session = await ingest_live_chunk(
        store,
        storage,
        speech_provider,
        conversation_id=conversation_id,
        audio_bytes=data,
        suffix=suffix,
        language_hint=None,
    )
    session = await maybe_regenerate_live_draft(
        store, llm_provider, conversation_id=conversation_id, session=session
    )
    return _to_response(session)


@router.get("/{conversation_id}/live", response_model=LiveSessionResponse)
async def get_live_session_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: LiveSessionStore = Depends(_get_live_store),
) -> LiveSessionResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:record"
    )
    session = await store.get(conversation_id)
    if session is None:
        return LiveSessionResponse(
            transcript_text="", draft_text=None, chunk_count=0, updated_at=""
        )
    return _to_response(session)


@router.delete("/{conversation_id}/live", status_code=status.HTTP_204_NO_CONTENT)
async def clear_live_session_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: LiveSessionStore = Depends(_get_live_store),
    _csrf: None = Depends(require_csrf),
) -> None:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="conversation:record"
    )
    await store.clear(conversation_id)
