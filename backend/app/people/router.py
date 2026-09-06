"""REST endpoints for KnownSpeaker CRUD. Every route enforces Permission +
Organization Membership, matching the Phase 9 longitudinal pattern
(`app.conversations.authz`) — a KnownSpeaker is org-scoped, not global.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import assert_organization_member_or_admin
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.people.api_schemas import (
    KnownSpeakerCreateRequest,
    KnownSpeakerResponse,
    KnownSpeakerUpdateRequest,
)
from app.people.models import KnownSpeaker
from app.people.service import create_known_speaker, list_known_speakers
from app.platform.db.session import get_session

router = APIRouter(prefix="/known-speakers", tags=["known-speakers"])

_require_read = require_permission("known-speaker:read")
_require_manage = require_permission("known-speaker:manage")


async def _get_known_speaker_or_404(db: AsyncSession, known_speaker_id: uuid.UUID) -> KnownSpeaker:
    known_speaker = await db.get(KnownSpeaker, known_speaker_id)
    if known_speaker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="known speaker not found")
    return known_speaker


@router.get("", response_model=list[KnownSpeakerResponse])
async def list_known_speakers_endpoint(
    organization_id: uuid.UUID,
    user: User = Depends(_require_read),
    db: AsyncSession = Depends(get_session),
) -> list[KnownSpeakerResponse]:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    known_speakers = await list_known_speakers(db, organization_id=organization_id)
    return [KnownSpeakerResponse.model_validate(k) for k in known_speakers]


@router.post("", response_model=KnownSpeakerResponse, status_code=status.HTTP_201_CREATED)
async def create_known_speaker_endpoint(
    organization_id: uuid.UUID,
    payload: KnownSpeakerCreateRequest,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> KnownSpeakerResponse:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    known_speaker = await create_known_speaker(
        db,
        organization_id=organization_id,
        display_name=payload.display_name,
        notes=payload.notes,
        created_by_user_id=user.id,
    )
    await record_event(
        db,
        event_type="known_speaker.created",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "organization_id": str(organization_id),
            "known_speaker_id": str(known_speaker.id),
        },
    )
    await db.commit()
    return KnownSpeakerResponse.model_validate(known_speaker)


@router.patch("/{known_speaker_id}", response_model=KnownSpeakerResponse)
async def update_known_speaker_endpoint(
    known_speaker_id: uuid.UUID,
    payload: KnownSpeakerUpdateRequest,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> KnownSpeakerResponse:
    known_speaker = await _get_known_speaker_or_404(db, known_speaker_id)
    await assert_organization_member_or_admin(
        db, user=user, organization_id=known_speaker.organization_id
    )
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(known_speaker, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="known_speaker.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"known_speaker_id": str(known_speaker_id)},
    )
    await db.commit()
    await db.refresh(known_speaker)
    return KnownSpeakerResponse.model_validate(known_speaker)


@router.delete("/{known_speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_known_speaker_endpoint(
    known_speaker_id: uuid.UUID,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    known_speaker = await _get_known_speaker_or_404(db, known_speaker_id)
    await assert_organization_member_or_admin(
        db, user=user, organization_id=known_speaker.organization_id
    )
    await db.delete(known_speaker)
    await record_event(
        db,
        event_type="known_speaker.deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"known_speaker_id": str(known_speaker_id)},
    )
    await db.commit()
