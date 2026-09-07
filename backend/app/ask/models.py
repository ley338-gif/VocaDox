"""Ask VocaDox domain model (post-GA P1-1).

`AskQuery` is an audit/history record of one question asked and its
(possibly empty) answer — never conversation/transcript content beyond
the already-extracted fact statements that made it into the answer,
matching this project's standing "no raw content in audit-adjacent
records" discipline. `answer_statements` stores exactly what
`app.ask.service.ask` returned to the caller: only statements whose
every citation was verified against a real `ExtractedFact` this user
was actually allowed to see. There is no path anywhere in this module
that stores an uncited/unverified statement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class AskQuery(Base):
    __tablename__ = "ask_queries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Nullable: a query with no explicit conversation scope and no
    # candidate evidence found has no single organization to attribute --
    # never guessed, left honestly NULL rather than forced onto an
    # arbitrary one of the asker's (possibly several) organizations.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    asked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Optional scope: only search this one conversation's facts. NULL means
    # "search everything this user can see" (org/team-scoped like search).
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"text": str, "fact_ids": [str, ...]}, ...] -- every fact_id here was
    # verified (app.ask.service._verify_statements) to reference a real,
    # currently-visible-to-this-user ExtractedFact. Never populated with an
    # unverified LLM claim.
    answer_statements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    had_candidate_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
