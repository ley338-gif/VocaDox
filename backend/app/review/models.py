"""Review issues (Phase 4): a minimal, honest, read-only surfacing of
uncertainty/contradiction signals (see app.intelligence.uncertainty and
app.intelligence.contradictions). This is NOT the Phase 5 Review Wizard —
no approval gating, no "3/5 reviewed" workflow, no correction UI lives
here. See docs/architecture/future-considerations.md for what's
deliberately deferred.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class ReviewIssueType(StrEnum):
    UNCERTAINTY = "uncertainty"
    POTENTIAL_CONTRADICTION = "potential_contradiction"


class ReviewIssueSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UncertaintyCategory(StrEnum):
    """Spec §25 — real, meaningful states, not decoration. Each is only
    ever set for a genuine reason (see app.intelligence.uncertainty for
    the classification logic that actually derives these from LLM output
    and transcript confidence, not a fixed default)."""

    LOW_TRANSCRIPTION_CONFIDENCE = "low_transcription_confidence"
    MISSING_CONTEXT = "missing_context"
    MISSING_EVIDENCE = "missing_evidence"
    INCOMPLETE_VALUE = "incomplete_value"
    AMBIGUOUS_TERM = "ambiguous_term"
    USER_REVIEW_REQUIRED = "user_review_required"


class ReviewIssueStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"  # Phase 5 will add resolution/correction; Phase 4 stops here.


class ReviewIssue(Base):
    __tablename__ = "review_issues"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Free-form sub-classification: an UncertaintyCategory value for
    # UNCERTAINTY issues, null for POTENTIAL_CONTRADICTION.
    uncertainty_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # JSON list of fact id strings this issue references — never the fact's
    # content itself (kept out of audit logs and this table alike; readers
    # follow the id to app.intelligence.models.ExtractedFact).
    related_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewIssueStatus.OPEN.value, index=True
    )
    issue_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
