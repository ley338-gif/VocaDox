"""SQLAlchemy ORM models for the conversation-capture domain (Phase 2).

Architecture (see docs/architecture/adr/0011-source-media-separation.md):
`Conversation` -> `MediaAsset` (source + derived) -> (future Transcript) ->
(future Evidence). This phase stops at immutable source media + metadata;
no transcription/diarization/AI interpretation happens here.

`ConversationType` and `PrivacyMode` are organizational/documentation hints
only — they must never gate or imply AI behavior (no hidden clinical
assumptions baked into the entity).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.session import Base

if TYPE_CHECKING:
    from app.media.models import MediaAsset


class ConversationType(StrEnum):
    """Organizational/documentation hint only. Extensible; never used to
    activate hidden AI behavior or encode clinical assumptions."""

    GENERAL = "general"
    MEDICAL = "medical"
    THERAPY = "therapy"
    MEETING = "meeting"
    INTERVIEW = "interview"
    OTHER = "other"


class ConversationStatus(StrEnum):
    """States that genuinely exist as of Phase 4. TRANSCRIBING/DIARIZING/
    ALIGNING became real in Phase 3 (real async processing stages — see
    app.processing). EXTRACTING became real in Phase 4 (LLM fact
    extraction, explicitly user-triggered — see app.intelligence).
    COMPOSING/APPROVED (and VALIDATING/REVIEW_REQUIRED/READY_FOR_APPROVAL)
    remain target-architecture-only (see docs/architecture/domain-model.md)
    and must not be produced by any Phase 4 code path — those are Phase
    5/6."""

    CREATED = "created"
    RECORDING = "recording"
    UPLOADED = "uploaded"
    NORMALIZING = "normalizing"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    ALIGNING = "aligning"
    READY = "ready"
    EXTRACTING = "extracting"
    FAILED = "failed"
    DELETED = "deleted"


class PrivacyMode(StrEnum):
    """RESTRICTED is represented in the model now so later phases don't
    need a schema change, but full restricted-sharing semantics (e.g.
    narrowing which org members may view a RESTRICTED conversation beyond
    ordinary permission+membership checks) are NOT implemented in Phase 2 —
    see docs/architecture/conversations.md, "Privacy mode: known gaps"."""

    STANDARD = "standard"
    RESTRICTED = "restricted"


class ParticipantType(StrEnum):
    UNKNOWN = "unknown"
    STAFF = "staff"
    PATIENT = "patient"
    CLIENT = "client"
    GUEST = "guest"
    OTHER = "other"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConversationType.GENERAL.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConversationStatus.CREATED.value, index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    privacy_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PrivacyMode.STANDARD.value
    )
    retention_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("retention_policies.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    participants: Mapped[list[ConversationParticipant]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    markers: Mapped[list[ConversationMarker]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    notes: Mapped[list[ConversationNote]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationParticipant(Base):
    """No unnecessary healthcare-specific required fields; display_name is
    a free-form label ("Person A", "Arzt", "Patient") — real names are
    never required. Speaker-cluster-to-participant mapping is a future
    (human-reviewed) diarization feature, NOT implemented here."""

    __tablename__ = "conversation_participants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ParticipantType.UNKNOWN.value
    )
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="participants")


class ConversationMarker(Base):
    """Manual bookmark placed during/after a recording. Not AI Evidence —
    just a human-created timestamp reference."""

    __tablename__ = "conversation_markers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="markers")


class ConversationNote(Base):
    """Manual user note. Conceptually `EVIDENCE_USER_CONTEXT` for the
    future Evidence engine (docs/architecture/domain-model.md) — the
    Evidence engine itself is not implemented here."""

    __tablename__ = "conversation_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="notes")


class RetentionPolicy(Base):
    """Retention foundation only — no scheduler executes these yet (see
    docs/architecture/conversations.md, "Retention: what's implemented").
    `retention_days=None` means "keep indefinitely", which is the explicit
    configurable default; production deployments must consciously choose a
    real value. This is NOT a GDPR-compliance claim by itself."""

    __tablename__ = "retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_source_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delete_derived_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
