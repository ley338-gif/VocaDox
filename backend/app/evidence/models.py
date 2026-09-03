"""Evidence linking (Phase 4): `FactEvidence` links one
`ExtractedFact` (app.intelligence.models) to the concrete
`TranscriptSegment`(s) that justify it — the non-negotiable Source ->
Facts provenance chain (docs/architecture/domain-model.md).

A fact with zero resolvable FactEvidence rows is marked
`FactStatus.UNVERIFIED` (app.intelligence.models) — never silently
dropped, never given a fabricated evidence link. See
app.intelligence.service.persist_extraction for where that decision is
made.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class EvidenceType(StrEnum):
    """See docs/architecture/domain-model.md's "Evidence types" table —
    the four real evidence sources plus the cross-cutting UNVERIFIED
    status is modeled on ExtractedFact.status, not here (this enum is only
    ever a real, resolved evidence source)."""

    EVIDENCE_SPOKEN = "evidence_spoken"
    EVIDENCE_USER_CONTEXT = "evidence_user_context"
    EVIDENCE_EXTERNAL_SYSTEM = "evidence_external_system"
    EVIDENCE_MANUAL = "evidence_manual"


class FactEvidence(Base):
    __tablename__ = "fact_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("extracted_facts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcript_segment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
