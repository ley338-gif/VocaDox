"""REST endpoints for VocabularyEntry CRUD (post-GA P0-3). Every route
enforces Permission + Organization Membership, matching the KnownSpeaker
pattern (`app.people.router`) — a vocabulary entry is org-scoped, not
global.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import assert_organization_member_or_admin
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.vocabulary.api_schemas import (
    VocabularyCreateRequest,
    VocabularyResponse,
    VocabularyUpdateRequest,
)
from app.vocabulary.models import VocabularyEntry
from app.vocabulary.service import (
    DuplicateVocabularyScopeError,
    create_vocabulary,
    delete_vocabulary,
    get_vocabulary,
    list_vocabulary,
)

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

_require_read = require_permission("vocabulary:read")
_require_manage = require_permission("vocabulary:manage")


async def _get_vocabulary_or_404(
    db: AsyncSession, *, organization_id: uuid.UUID, entry_id: uuid.UUID
) -> VocabularyEntry:
    entry = await get_vocabulary(db, organization_id=organization_id, entry_id=entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vocabulary entry not found"
        )
    return entry


@router.get("", response_model=list[VocabularyResponse])
async def list_vocabulary_endpoint(
    organization_id: uuid.UUID,
    user: User = Depends(_require_read),
    db: AsyncSession = Depends(get_session),
) -> list[VocabularyResponse]:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    entries = await list_vocabulary(db, organization_id=organization_id)
    return [VocabularyResponse.model_validate(e) for e in entries]


@router.post("", response_model=VocabularyResponse, status_code=status.HTTP_201_CREATED)
async def create_vocabulary_endpoint(
    organization_id: uuid.UUID,
    payload: VocabularyCreateRequest,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> VocabularyResponse:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    try:
        entry = await create_vocabulary(
            db,
            organization_id=organization_id,
            template_id=payload.template_id,
            name=payload.name,
            terms=payload.terms,
            initial_prompt=payload.initial_prompt,
            created_by_user_id=user.id,
        )
    except DuplicateVocabularyScopeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await record_event(
        db,
        event_type="vocabulary.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"organization_id": str(organization_id), "vocabulary_id": str(entry.id)},
    )
    await db.commit()
    return VocabularyResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=VocabularyResponse)
async def update_vocabulary_endpoint(
    entry_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: VocabularyUpdateRequest,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> VocabularyResponse:
    entry = await _get_vocabulary_or_404(db, organization_id=organization_id, entry_id=entry_id)
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(entry, field, value)
    await db.flush()
    await record_event(
        db,
        event_type="vocabulary.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"vocabulary_id": str(entry_id)},
    )
    await db.commit()
    await db.refresh(entry)
    return VocabularyResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vocabulary_endpoint(
    entry_id: uuid.UUID,
    organization_id: uuid.UUID,
    user: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    entry = await _get_vocabulary_or_404(db, organization_id=organization_id, entry_id=entry_id)
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    await delete_vocabulary(db, entry)
    await record_event(
        db,
        event_type="vocabulary.deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"vocabulary_id": str(entry_id)},
    )
    await db.commit()
