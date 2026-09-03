"""Fact extraction domain models (Phase 4).

`ExtractedFact` is a single structured fact derived from a conversation's
transcript by the LLM extraction pipeline (see app.intelligence.service).
Every fact traces back to: Conversation -> SourceMedia/Transcript ->
ProcessingRun (processing_run_id) -> specific TranscriptSegment(s), the
latter via app.evidence.models.FactEvidence — never a Fact without at
least an attempted evidence link (see FactStatus.UNVERIFIED for what
happens when no evidence resolves).

`structured_value` holds the category-specific Pydantic-validated payload
(app.intelligence.schemas) as JSON — never raw/unvalidated LLM text.
`category` picks which schema it was validated against.

The three-layer model (ADR-0004, docs/architecture/domain-model.md's
Ramipril example): SOURCE (transcript_segment) -> FACT (this table) ->
DOCUMENT (Phase 5, not built here). Never `LLM -> Truth` directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class FactCategory(StrEnum):
    """Narrow, well-defined extraction categories (spec §23/§24: modular
    extraction with per-category schemas, never one unconstrained prompt).
    Deliberately domain-neutral — VocaDox is not medical-only (spec
    §1/§6); domain-specific categories are a future Template concern
    (Phase 6), not hardcoded here."""

    GENERAL_FACT = "general_fact"
    DECISION = "decision"
    TASK = "task"


class FactStatus(StrEnum):
    VERIFIED = "verified"  # has at least one resolved fact_evidence row
    UNVERIFIED = "unverified"  # no evidence could be linked — never silently dropped
    SUPERSEDED = "superseded"  # a later extraction run replaced it (re-extraction)


class Certainty(StrEnum):
    """What the LLM itself reported about a field/fact — mirrors
    app.intelligence.schemas.Certainty exactly; kept as a separate enum
    here (not imported from schemas) so the ORM layer never depends on the
    Pydantic schema module, matching the module-boundary pattern used by
    app.transcription.models vs app.providers.speech_to_text."""

    STATED = "stated"
    UNCLEAR = "unclear"
    INCOMPLETE = "incomplete"
    NOT_MENTIONED = "not_mentioned"


class ExtractedFact(Base):
    __tablename__ = "extracted_facts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Category-specific, Pydantic-validated payload (app.intelligence.schemas) —
    # never raw/unvalidated LLM text.
    structured_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    certainty: Mapped[str] = mapped_column(String(16), nullable=False)
    # Model-reported/derived confidence in [0,1]; None when the provider
    # gives no calibrated signal — never fabricated as a fake 1.0.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FactStatus.UNVERIFIED.value, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
