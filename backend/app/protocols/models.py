"""Protokoll domain (Post-GA): a structured, chronological representation
of a conversation — sections/topics, important points, decisions, open
questions, action items — distinct from both Transkript (verbatim,
timestamped, source of truth) and Dokumentation (a formal generated
document, deterministic composition, no free narrative summary). See
docs/architecture/adr/0042-protokoll.md for the full design rationale.

Mirrors `app.documents.models`' `Document`/`DocumentRevision` shape
closely: `Protocol` is the stable per-conversation identity,
`ProtocolRevision` is one immutable snapshot (every "Neu erstellen"
click creates a new one — nothing is ever silently overwritten). Unlike
`DocumentRevision.structured_content` (one JSON blob — fine there since
Documents are never edited section-by-section), a revision's content
here is normalized child rows (`ProtocolSection`/`ProtocolItem`) so a
future PR can PATCH an individual section/item without rewriting a whole
blob.

Generation is LLM-driven (unlike Document composition, which is
deterministic — see that module's own docstring for why that one
correctly runs synchronously). `ProtocolSource` mirrors
`app.evidence.models.FactEvidence`: every section/item's claimed
transcript evidence becomes a real row only once resolved against an
actual `TranscriptSegment` of the same transcript — a hallucinated
citation is silently dropped, never trusted (see
`app.protocols.service.run_protocol_generation`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class ProtocolRevisionStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class ProtocolSectionType(StrEnum):
    """Generic, domain-neutral section types (never hardcoded to
    medical-only names — a template/domain decides which subset actually
    appears and what title the LLM gives each instance)."""

    INTRODUCTION = "introduction"
    TOPIC = "topic"
    FACTS = "facts"
    DISCUSSION = "discussion"
    DECISION = "decision"
    ACTION_ITEMS = "action_items"
    OPEN_QUESTIONS = "open_questions"
    NOTE = "note"
    CONCLUSION = "conclusion"


class ProtocolItemType(StrEnum):
    IMPORTANT_POINT = "important_point"
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    OPEN_QUESTION = "open_question"
    FACT = "fact"
    NOTE = "note"


class Protocol(Base):
    """One per conversation (spec: a conversation's protocol identity).
    `current_revision_id` always points at the latest revision — reading
    `GET /conversations/{id}/protocol` never needs to compute "latest" by
    scanning `protocol_revisions` itself, mirrors `Document`."""

    __tablename__ = "protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("protocol_revisions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProtocolRevision(Base):
    """One immutable snapshot of a generated protocol. `revision_number`
    is 1-based and monotonically increasing per protocol (never reused,
    never decremented) — same discipline as `DocumentRevision`.
    `status=GENERATING` exists so a `GET` while the async job is still
    running has a real row to report progress against (created up front
    by `app.protocols.service.run_protocol_generation`, flipped to
    READY/FAILED once the LLM call resolves)."""

    __tablename__ = "protocol_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProtocolRevisionStatus.GENERATING.value, index=True
    )
    # Nullable: a FAILED revision may never have gotten far enough to
    # create a ProcessingRun row's counterpart here in edge cases, though
    # in practice the run is created before generation starts.
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ProtocolSection(Base):
    __tablename__ = "protocol_sections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocol_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    section_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # LLM-reported confidence for this section as a whole, if the provider
    # returns one — never fabricated when absent (see ExtractedFact's own
    # `confidence` column for the identical convention).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Unused until the follow-up editing PR (see ADR-0042) -- the column
    # ships now so that PR is additive, never a migration that changes
    # this table's shape again.
    manually_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProtocolItem(Base):
    __tablename__ = "protocol_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocol_sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Only ever meaningful for item_type == action_item -- free text, not
    # a Participant FK, matching how app.intelligence's own "task" category
    # already models `assignee`/`decided_by` (Phase 4 ExtractedFact
    # structured_value) as free text rather than a resolved participant
    # link, since the LLM only ever has a speaker label to go on.
    responsible_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    manually_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProtocolSource(Base):
    """Mirrors `app.evidence.models.FactEvidence` exactly: a resolved link
    from one section-or-item to one real transcript segment. Exactly one
    of `protocol_section_id`/`protocol_item_id` is set (enforced by the
    CheckConstraint below) — never both, never neither."""

    __tablename__ = "protocol_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("protocol_sections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    protocol_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("protocol_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    transcript_segment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(protocol_section_id IS NOT NULL) != (protocol_item_id IS NOT NULL)",
            name="ck_protocol_source_exactly_one_parent",
        ),
    )
