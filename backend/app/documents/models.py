"""Document composition + revision domain (Phase 5).

Implements the spec's DRAFT -> REVIEW_REQUIRED -> READY_FOR_APPROVAL ->
APPROVED workflow (spec §27) and §31's non-destructive revision history:
an `Document` row is the stable identity ("the document for this
conversation"); a `DocumentRevision` row is one immutable-once-approved
snapshot of composed content. **The AI must never set APPROVED** — see
`app.documents.service.approve_document`, the only place that ever writes
that status, and it is only ever reachable from a route that requires the
`document:approve` permission held by a human user.

Composition is deterministic, never an LLM "write a report" call (spec
§23's rejected architecture) — see `app.documents.service.compose_document`.
Every section/statement in `structured_content` carries the `fact_ids` it
was rendered from, so the chain Source -> Facts -> Document
(`docs/architecture/domain-model.md`) never breaks.

Immutability of an APPROVED revision is enforced by a SQLAlchemy
`before_update` listener below (`_forbid_mutating_approved_revision`), not
just "no route happens to call update" — see
`tests/documents/test_revisions.py::test_approved_revision_is_immutable`
for the proof.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class DocumentRevisionStatus(StrEnum):
    """Spec §27's workflow. The AI/system may only ever produce DRAFT,
    REVIEW_REQUIRED, or READY_FOR_APPROVAL (see
    app.documents.service.compose_document) — APPROVED is exclusively set
    by app.documents.service.approve_document, which requires a human user
    holding `document:approve` and no unresolved HIGH/CRITICAL review
    issue."""

    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"


class ImmutableRevisionError(RuntimeError):
    """Raised by the ORM-level guard below — an APPROVED DocumentRevision
    was about to be mutated. This is a modeling bug in whatever code
    triggered it, never an expected/caught condition in normal operation."""


class Document(Base):
    """One per conversation (spec: a conversation's composed document).
    `current_revision_id` always points at the latest revision — reading
    `GET /conversations/{id}/document` never needs to compute "latest" by
    scanning `document_revisions` itself."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentRevisionStatus.DRAFT.value, index=True
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentRevision(Base):
    """One immutable-once-APPROVED snapshot of composed content (spec §31:
    "never destructively overwrite"). `structured_content` is a list of
    section dicts, each `{category, title, statements: [{text, fact_ids}]}`
    — every statement traceable back to the ExtractedFact(s) it was
    rendered from (never free text with no fact_ids). `rendered_text` is
    the same content flattened to plain text for a quick read/export.

    `revision_number` is 1-based and monotonically increasing per
    document — see app.documents.service.compose_document for how it's
    assigned (never reused, never decremented)."""

    __tablename__ = "document_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    structured_content: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentRevisionStatus.DRAFT.value, index=True
    )

    # Denormalized so "what blocked/allowed this revision's status" survives
    # even after the underlying review issues are later resolved — never
    # recomputed retroactively from current review_issues state.
    blocking_issue_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


@event.listens_for(DocumentRevision, "before_update")
def _forbid_mutating_approved_revision(
    mapper: object, connection: object, target: DocumentRevision
) -> None:  # noqa: ARG001 - mapper/connection are part of SQLAlchemy's event signature, unused here
    """Real, ORM-enforced immutability (spec §31) — not a UI convention.
    Allows exactly one legitimate update: the transition INTO APPROVED
    (previous committed status was READY_FOR_APPROVAL). Once the
    previously-committed status is already APPROVED, ANY further UPDATE to
    this row is rejected before it reaches the database. New content after
    that point must go through app.documents.service.compose_document,
    which always INSERTs a new DocumentRevision row instead."""
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(target).attrs.status.history
    previous_status = None
    if history.deleted:
        previous_status = history.deleted[0]
    elif history.unchanged:
        previous_status = history.unchanged[0]
    if previous_status == DocumentRevisionStatus.APPROVED.value:
        raise ImmutableRevisionError(
            f"document_revisions.id={target.id} is APPROVED and can never be modified; "
            "create a new revision via compose_document instead"
        )
