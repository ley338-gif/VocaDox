"""Follow-up/Task domain model (Phase 9, spec §41).

A `FollowUpTask` is a generic, domain-neutral action item — never a
medical-specific type (that belongs in Templates, Phase 6). Two sources:

- `AI_EXTRACTED`: derived from an existing `app.intelligence.models
  .ExtractedFact` with `category == "task"` (Phase 4's existing TASK
  extraction category — no parallel fact type was invented). `source_fact_id`
  always points back at the originating fact for AI_EXTRACTED rows; a human
  never loses the ability to trace an AI-suggested task to its evidence.
- `USER_CREATED`: a human adds a follow-up directly, not derived from any
  transcript. `source_fact_id` is NULL.

No notification/reminder/email system exists here (Phase 10 territory) —
this is a real, listable/actionable task view only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class FollowUpSource(StrEnum):
    AI_EXTRACTED = "ai_extracted"
    USER_CREATED = "user_created"


class FollowUpStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    DISMISSED = "dismissed"


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Denormalized organization_id (also reachable via conversation) so
    # cross-organization queries/isolation checks never need a join to be
    # correct — mirrors app.conversations.models.Conversation's own
    # organization_id-on-every-row pattern.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Only set (and only meaningful) for source == AI_EXTRACTED; NULL for
    # USER_CREATED. ON DELETE SET NULL: if the originating fact is ever
    # removed, the task itself survives (it's a real independent action
    # item once created) but loses its evidence link, which is a real,
    # visible state change, never silently invented.
    source_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True
    )

    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    due_date: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # free-form date/time phrase, matches app.intelligence.schemas.TaskItem.due_date

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FollowUpStatus.OPEN.value, index=True
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
