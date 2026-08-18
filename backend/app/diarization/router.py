"""REST endpoints for DetectedSpeaker read/assignment — human-controlled
mapping only (spec: never automatic, never voice-biometric identity)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import authorize_conversation_access
from app.conversations.models import ConversationParticipant
from app.diarization.schemas import DetectedSpeakerResponse, SpeakerAssignmentRequest
from app.diarization.service import assign_speaker, get_speaker, list_speakers, unassign_speaker
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.platform.db.session import get_session

router = APIRouter(prefix="/conversations", tags=["diarization"])


@router.get("/{conversation_id}/speakers", response_model=list[DetectedSpeakerResponse])
async def list_speakers_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[DetectedSpeakerResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="speaker:read"
    )
    speakers = await list_speakers(db, conversation_id=conversation_id)
    return [DetectedSpeakerResponse.model_validate(s) for s in speakers]


@router.patch("/{conversation_id}/speakers/{speaker_id}", response_model=DetectedSpeakerResponse)
async def assign_speaker_endpoint(
    conversation_id: uuid.UUID,
    speaker_id: uuid.UUID,
    body: SpeakerAssignmentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> DetectedSpeakerResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="speaker:assign"
    )
    speaker = await get_speaker(db, conversation_id=conversation_id, speaker_id=speaker_id)
    if speaker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="speaker not found")

    if body.participant_id is not None:
        result = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.id == body.participant_id,
                ConversationParticipant.conversation_id == conversation_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="participant not found on this conversation",
            )

    if body.participant_id is None and body.display_label is None:
        await unassign_speaker(db, speaker)
        event_type = "speaker.unassigned"
    else:
        await assign_speaker(
            db,
            speaker,
            participant_id=body.participant_id,
            display_label=body.display_label,
            assigned_by_user_id=user.id,
        )
        event_type = "speaker.assigned"

    await record_event(
        db, event_type=event_type, user_id=user.id, event_metadata={"speaker_id": str(speaker.id)}
    )
    await db.commit()
    return DetectedSpeakerResponse.model_validate(speaker)
