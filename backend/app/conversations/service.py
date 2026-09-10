"""Conversation domain service: creation, status transitions, participants,
markers, notes, and deletion semantics. Every `Conversation.status` write
goes through `apply_status_transition` (which delegates to
`app.conversations.state_machine.transition`) — nothing else may assign
`.status` directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
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
from app.identity.models import User
from app.longitudinal.models import FollowUpTask
from app.media.models import MediaAsset
from app.organizations.service import user_can_access_organization
from app.profiles.service import get_processing_profile_by_key
from app.providers.storage import StorageProvider
from app.search.service import delete_search_entries_for_conversation

# A visible, overridable pre-fill for `processing_profile_id` when the
# caller didn't pick one explicitly -- NOT the "hidden AI behavior"
# `ConversationType.__doc__` warns against: the resolved id is stored as a
# normal, GET-visible, PATCH-editable column exactly like an explicit
# choice would be, and `app.profiles.resolver` explains its effect via
# `field_sources` the same way either way. GENERAL is deliberately absent
# -- it's already what the SYSTEM DEFAULT layer resolves to, so pre-filling
# it would only relabel `field_sources` from "system_default" to
# "processing_profile" for no behavioral difference. THERAPY/INTERVIEW/
# OTHER have no matching published profile yet and fall through to the
# system default, same as before this existed.
_TYPE_DEFAULT_PROFILE_KEY: dict[ConversationType, str] = {
    ConversationType.MEDICAL: "medical_consultation",
    ConversationType.MEETING: "meeting",
}


async def _resolve_default_profile_id(
    session: AsyncSession, conversation_type: ConversationType
) -> uuid.UUID | None:
    key = _TYPE_DEFAULT_PROFILE_KEY.get(conversation_type)
    if key is None:
        return None
    profile = await get_processing_profile_by_key(session, key)
    if profile is None or not profile.enabled or profile.current_published_version_id is None:
        return None
    return profile.id


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
    group_id: uuid.UUID | None = None,
) -> Conversation:
    if processing_profile_id is None:
        processing_profile_id = await _resolve_default_profile_id(session, conversation_type)

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
        group_id=group_id,
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
    group_ids: set[uuid.UUID] | None = None,
    status_filter: str | None = None,
    type_filter: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Conversation], int]:
    """`group_ids=None` means the caller can see every team (system:admin
    or conversation:read-cross-team) -- no team filter applied. Otherwise a
    conversation is visible if it has no team (group_id IS NULL, same
    "org-wide" semantics as today's pre-team-scoping data) or its team is
    in `group_ids` -- mirrors app.conversations.authz.authorize_
    conversation_access's per-row logic for this cross-conversation list."""
    stmt = select(Conversation).where(Conversation.status != ConversationStatus.DELETED.value)
    if organization_ids is not None:
        stmt = stmt.where(Conversation.organization_id.in_(organization_ids))
    if group_ids is not None:
        stmt = stmt.where(
            or_(Conversation.group_id.is_(None), Conversation.group_id.in_(group_ids))
        )
    if status_filter:
        # Comma-separated multi-value support (post-GA redesign: the
        # Gespräche list's "In Bearbeitung" tab groups several real
        # statuses into one filter) -- a single value with no comma
        # behaves identically to the old exact-match filter.
        statuses = [s for s in status_filter.split(",") if s]
        stmt = stmt.where(Conversation.status.in_(statuses))
    if type_filter:
        stmt = stmt.where(Conversation.conversation_type == type_filter)
    if search:
        stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))

    count_result = await session.execute(stmt)
    total = len(count_result.all())

    stmt = stmt.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def conversation_status_counts(
    session: AsyncSession,
    *,
    organization_ids: set[uuid.UUID] | None,
    group_ids: set[uuid.UUID] | None = None,
) -> dict[str, int]:
    """Real per-status conversation counts (GROUP BY, never fabricated) for
    the app dashboard's KPI cards — mirrors the existing
    `app.administration.service.queue_counts()` aggregate-query pattern.
    Excludes DELETED conversations, matching `list_conversations`'s default
    scope. Statuses with zero conversations are simply absent from the
    returned dict rather than included as 0. `group_ids` follows the same
    "None = every team, otherwise NULL-team-or-in-set" semantics as
    `list_conversations` — a non-privileged user's dashboard shouldn't show
    cross-team totals either."""
    stmt = (
        select(Conversation.status, func.count())
        .where(Conversation.status != ConversationStatus.DELETED.value)
        .group_by(Conversation.status)
    )
    if organization_ids is not None:
        stmt = stmt.where(Conversation.organization_id.in_(organization_ids))
    if group_ids is not None:
        stmt = stmt.where(
            or_(Conversation.group_id.is_(None), Conversation.group_id.in_(group_ids))
        )
    result = await session.execute(stmt)
    return {status_value: int(count) for status_value, count in result.all()}


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

    # FollowUpTask has no soft-delete concept of its own (see its model
    # docstring -- it's a derived/denormalized view of the conversation, not
    # an independent record), so a deleted conversation's tasks are hard-
    # deleted here rather than left behind to keep showing up in the
    # org-wide Aufgaben list forever.
    await session.execute(
        delete(FollowUpTask).where(FollowUpTask.conversation_id == conversation.id)
    )

    # Same reasoning as FollowUpTask above -- a deleted conversation's
    # content must not keep surfacing in cross-conversation search
    # (post-GA P0-1).
    await delete_search_entries_for_conversation(session, conversation_id=conversation.id)


# -- Participants -------------------------------------------------------


class ParticipantUserNotFoundError(Exception):
    """`user_id` does not reference an active `User`."""


class ParticipantUserNotInOrganizationError(Exception):
    """`user_id` resolves to a user outside the conversation's
    organization (and without `system:admin`)."""


class ParticipantUserAlreadyLinkedError(Exception):
    """`user_id` is already linked to another participant of this same
    conversation."""


async def resolve_participant_user(
    session: AsyncSession,
    *,
    conversation: Conversation,
    user_id: uuid.UUID,
    exclude_participant_id: uuid.UUID | None = None,
) -> User:
    """Shared validation for linking a registered user to a conversation
    participant -- used by both `app.conversations.router` (POST/PATCH
    `/conversations/{id}/participants`) and `app.integrations.router`
    (the equivalent service-account API), so the two surfaces can never
    drift apart on what counts as a valid link. Raises one of the three
    domain errors above (never HTTPException -- this is a service-layer
    function, translating to the right HTTP status is each router's job)
    on the first failing check; returns the resolved, active `User`
    otherwise. Deliberately does NOT touch `display_name` -- the
    "fall back to the user's name when none was supplied" rule only
    applies on participant *creation* and is each router's job, not
    this shared validator's.
    """
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise ParticipantUserNotFoundError(str(user_id))

    if not await user_can_access_organization(
        session, user_id=user.id, organization_id=conversation.organization_id
    ):
        raise ParticipantUserNotInOrganizationError(str(user_id))

    stmt = select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id == user_id,
    )
    if exclude_participant_id is not None:
        stmt = stmt.where(ConversationParticipant.id != exclude_participant_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise ParticipantUserAlreadyLinkedError(str(user_id))

    return user


async def add_participant(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    display_name: str,
    participant_type: ParticipantType = ParticipantType.UNKNOWN,
    external_reference: str | None = None,
    notes: str | None = None,
    known_speaker_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> ConversationParticipant:
    participant = ConversationParticipant(
        conversation_id=conversation_id,
        display_name=display_name,
        participant_type=participant_type.value,
        external_reference=external_reference,
        notes=notes,
        known_speaker_id=known_speaker_id,
        user_id=user_id,
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
