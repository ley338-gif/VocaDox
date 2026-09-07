"""`KnownSpeaker` domain model — see app/people/__init__.py for the
feature's scope and the deliberate metadata-only (no biometrics) choice.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class KnownSpeaker(Base):
    """One persistent, named identity per organization. Linked from zero
    or more `ConversationParticipant` rows (app.conversations.models) —
    never linked directly from a `DetectedSpeaker`; a detected speaker is
    assigned to a participant first (app.diarization's existing
    participant_id linkage), and the participant optionally carries a
    KnownSpeaker so the *next* conversation's participant list can offer
    "this is the same person" instead of retyping the name.

    `voiceprint_embedding` (post-GA P1-2) is the running-average pyannote
    embedding for this person, populated only by an explicit human
    enrollment action (app.people.service.enroll_voiceprint) — never
    written automatically. It is used only to *suggest* a match on a
    future DetectedSpeaker (app.diarization.service.suggest_known_speakers);
    the suggestion is always confidence-scored and never silently applied
    (see app.diarization.models.DetectedSpeaker's docstring on the same
    principle for participant_id).
    """

    __tablename__ = "known_speakers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voiceprint_embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    voiceprint_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voiceprint_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def has_voiceprint(self) -> bool:
        return self.voiceprint_embedding is not None
