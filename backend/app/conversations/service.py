"""Conversation domain service: creation, status transitions, participants,
markers, notes, and deletion semantics. Every `Conversation.status` write
goes through `apply_status_transition` (which delegates to
`app.conversations.state_machine.transition`) — nothing else may assign
`.status` directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import (
    Conversation,
    ConversationMarker,
    ConversationNote,
    ConversationParticipant,
    ConversationStatus,
    ConversationType,
    ParticipantType,
    PrivacyMode,
)
from app.conversations.state_machine import transition
from app.media.models import MediaAsset
from app.providers.storage import StorageProvider


async def create_conversation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    title: str,
    description: str | None = None,
    conversation_type: ConversationType = ConversationType.GENERAL,
    external_reference: str | None = None,
    external_reference_type: str | None = None,
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD,
    retention_policy_id: uuid.UUID | None = None,
    processing_profile_id: uuid.UUID | None = None,
) -> Conversation:
    conversation = Conversation(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        title=title,
        description=description,
        conversation_type=conversation_type.value,
        status=ConversationStatus.CREATED.value,
        external_reference=external_reference,
        external_reference_type=external_reference_type,
        privacy_mode=privacy_mode.value,
        retention_policy_id=retention_policy_id,
        processing_profile_id=processing_profile_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation


def apply_status_transition(conversation: Conversation, target: ConversationStatus) -> None:
    current = ConversationStatus(conversation.status)
    new_status = transition(current, target)
    conversation.status = new_status.value
    if new_status == ConversationStatus.RECORDING and conversation.started_at is None:
        conversation.started_at = datetime.now(UTC)
    if new_status in (ConversationStatus.UPLOADED,) and conversation.ended_at is None:
        conversation.ended_at = datetime.now(UTC)


async def list_conversations(
    session: AsyncSession,
    *,
    organization_ids: set[uuid.UUID] | None,
    status_filter: str | None = None,
    type_filter: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Conversation], int]:
    stmt = select(Conversation).where(Conversation.status != ConversationStatus.DELETED.value)
    if organization_ids is not None:
        stmt = stmt.where(Conversation.organization_id.in_(organization_ids))
    if status_filter:
        stmt = stmt.where(Conversation.status == status_filter)
    if type_filter:
        stmt = stmt.where(Conversation.conversation_type == type_filter)
    if search:
        stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))

    count_result = await session.execute(stmt)
    total = len(count_result.all())

    stmt = stmt.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def soft_delete_conversation(
    session: AsyncSession, conversation: Conversation, *, storage: StorageProvider
) -> None:
    """Soft-deletes the Conversation row AND destroys the physical media
    bytes on disk (never "soft delete in the DB but audio still on disk" —
    see docs/architecture/conversations.md, "Deletion semantics"). Retains
    the MediaAsset rows themselves (with `deleted_at` set) as minimal
    justified audit metadata — never retains the audio content."""
    apply_status_transition(conversation, ConversationStatus.DELETED)
    conversation.deleted_at = datetime.now(UTC)

    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.conversation_id == conversation.id, MediaAsset.deleted_at.is_(None)
        )
    )
    for media in result.scalars().all():
        await storage.delete(media.storage_key)
        media.deleted_at = datetime.now(UTC)


# -- Participants -------------------------------------------------------


async def add_participant(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    display_name: str,
    participant_type: ParticipantType = ParticipantType.UNKNOWN,
    external_reference: str | None = None,
    notes: str | None = None,
) -> ConversationParticipant:
    participant = ConversationParticipant(
        conversation_id=conversation_id,
        display_name=display_name,
        participant_type=participant_type.value,
        external_reference=external_reference,
        notes=notes,
    )
    session.add(participant)
    await session.flush()
    return participant


# -- Markers --------------------------------------------------------------


async def add_marker(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    timestamp_ms: int,
    label: str | None = None,
    note: str | None = None,
) -> ConversationMarker:
    if timestamp_ms < 0:
        raise ValueError("marker timestamp_ms must be >= 0")
    marker = ConversationMarker(
        conversation_id=conversation_id,
        created_by_user_id=created_by_user_id,
        timestamp_ms=timestamp_ms,
        label=label,
        note=note,
    )
    session.add(marker)
    await session.flush()
    return marker


# -- Notes ------------------------------------------------------------------


async def add_note(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    content: str,
    timestamp_ms: int | None = None,
) -> ConversationNote:
    if not content.strip():
        raise ValueError("note content must not be empty")
    note = ConversationNote(
        conversation_id=conversation_id,
        created_by_user_id=created_by_user_id,
        content=content,
        timestamp_ms=timestamp_ms,
    )
    session.add(note)
    await session.flush()
    return note
