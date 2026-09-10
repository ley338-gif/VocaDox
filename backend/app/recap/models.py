"""`Recap`/`RecapRevision` domain model — see app/recap/__init__.py for
scope and why this is a separate artifact from Document/DocumentRevision.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class RecapStatus(StrEnum):
    """The AI/system may only ever produce DRAFT (see
    app.recap.service.generate_recap) — APPROVED is exclusively set by
    app.recap.service.approve_recap, which requires a human user holding
    `recap:approve`."""

    DRAFT = "draft"
    APPROVED = "approved"


class ImmutableRecapRevisionError(RuntimeError):
    """Raised by the ORM-level guard below — an APPROVED RecapRevision was
    about to be mutated. Mirrors
    app.documents.models.ImmutableRevisionError exactly."""


class Recap(Base):
    """One per conversation. `current_revision_id` always points at the
    latest revision."""

    __tablename__ = "recaps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RecapStatus.DRAFT.value, index=True
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recap_revisions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RecapRevision(Base):
    """One immutable-once-APPROVED snapshot of generated recap text —
    mirrors app.documents.models.DocumentRevision's shape/discipline.
    Re-generating always INSERTs a new revision, never mutates an
    existing one."""

    __tablename__ = "recap_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    recap_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recaps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # BCP-47-ish language tag the recap was written in (mirrors the
    # transcript's own detected/spoken language) — informational only,
    # nothing currently branches on it.
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(256), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RecapStatus.DRAFT.value, index=True
    )

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


@event.listens_for(RecapRevision, "before_update")
def _forbid_mutating_approved_recap_revision(
    mapper: object, connection: object, target: RecapRevision
) -> None:  # noqa: ARG001 - mapper/connection are part of SQLAlchemy's event signature, unused here
    """Real, ORM-enforced immutability — not a UI convention. Mirrors
    app.documents.models._forbid_mutating_approved_revision exactly.
    Allows exactly one legitimate update: the transition INTO APPROVED.
    Once the previously-committed status is already APPROVED, ANY further
    UPDATE to this row is rejected before it reaches the database."""
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(target).attrs.status.history
    previous_status = None
    if history.deleted:
        previous_status = history.deleted[0]
    elif history.unchanged:
        previous_status = history.unchanged[0]
    if previous_status == RecapStatus.APPROVED.value:
        raise ImmutableRecapRevisionError(
            f"recap_revisions.id={target.id} is APPROVED and can never be modified; "
            "create a new revision via generate_recap instead"
        )


class RecapShareLink(Base):
    """Post-GA P3-2: a time-limited, unauthenticated-access token for one
    conversation's currently-approved recap — e.g. to send to a patient
    or referring practice without giving them a VocaDox login. The bearer
    `token` is a cryptographically random, unguessable string
    (`secrets.token_urlsafe`, see app.recap.service.create_share_link) —
    never derived from or containing any identifying data, same posture
    as `app.identity.sessions.SessionData`'s own session tokens. Only its
    SHA-256 digest is stored, so database/API-list access cannot recover a
    reusable public URL; the raw token is returned exactly once on create.

    Access is validated purely by (token exists, not expired, not
    revoked) at request time — the recap CONTENT served is always the
    live current-revision content at the moment of access, never a
    frozen copy, so revoking approval or generating a new revision takes
    effect on every outstanding link immediately."""

    __tablename__ = "recap_share_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
