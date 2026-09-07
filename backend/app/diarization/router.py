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
from app.diarization.schemas import (
    DetectedSpeakerResponse,
    SpeakerAssignmentRequest,
    SpeakerEnrollRequest,
)
from app.diarization.service import (
    SuggestionNotAvailableError,
    accept_suggestion,
    assign_speaker,
    get_speaker,
    list_speakers,
    unassign_speaker,
)
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.people.models import KnownSpeaker
from app.people.service import VoiceprintDimensionMismatchError, enroll_voiceprint
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
    await db.refresh(speaker)
    return DetectedSpeakerResponse.model_validate(speaker)


@router.post(
    "/{conversation_id}/speakers/{speaker_id}/enroll", response_model=DetectedSpeakerResponse
)
async def enroll_speaker_voiceprint_endpoint(
    conversation_id: uuid.UUID,
    speaker_id: uuid.UUID,
    body: SpeakerEnrollRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> DetectedSpeakerResponse:
    """Explicit human action: "this detected speaker's voice really is
    this known person" — folds the speaker's embedding into that
    KnownSpeaker's running-average voiceprint (app.people.service.
    enroll_voiceprint). Requires both speaker:assign (conversation-scoped)
    and known-speaker:manage (this mutates an org-wide KnownSpeaker),
    mirroring the same two-permission gate the frontend already applies
    to "remember as known person"."""
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="speaker:assign"
    )
    permissions = await get_user_permissions(db, user.id)
    if "known-speaker:manage" not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    speaker = await get_speaker(db, conversation_id=conversation_id, speaker_id=speaker_id)
    if speaker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="speaker not found")
    if speaker.embedding is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no voiceprint available for this speaker",
        )

    known_speaker = await db.get(KnownSpeaker, body.known_speaker_id)
    if known_speaker is None or known_speaker.organization_id != conversation.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="known speaker not found")

    try:
        await enroll_voiceprint(db, known_speaker, embedding=speaker.embedding)
    except VoiceprintDimensionMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await record_event(
        db,
        event_type="known_speaker.voiceprint_enrolled",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "known_speaker_id": str(known_speaker.id),
            "speaker_id": str(speaker.id),
            "conversation_id": str(conversation_id),
        },
    )
    await db.commit()
    await db.refresh(speaker)
    return DetectedSpeakerResponse.model_validate(speaker)


@router.post(
    "/{conversation_id}/speakers/{speaker_id}/accept-suggestion",
    response_model=DetectedSpeakerResponse,
)
async def accept_speaker_suggestion_endpoint(
    conversation_id: uuid.UUID,
    speaker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> DetectedSpeakerResponse:
    """Turns a pending confidence-scored suggestion into a real assignment
    — same permission as any other manual assignment, since that's what
    this ultimately is; the suggestion only pre-fills *which* KnownSpeaker,
    never assigns anything by itself."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="speaker:assign"
    )
    speaker = await get_speaker(db, conversation_id=conversation_id, speaker_id=speaker_id)
    if speaker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="speaker not found")

    try:
        await accept_suggestion(
            db, speaker, conversation_id=conversation_id, assigned_by_user_id=user.id
        )
    except SuggestionNotAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await record_event(
        db,
        event_type="speaker.suggestion_accepted",
        user_id=user.id,
        event_metadata={"speaker_id": str(speaker.id)},
    )
    await db.commit()
    await db.refresh(speaker)
    return DetectedSpeakerResponse.model_validate(speaker)
