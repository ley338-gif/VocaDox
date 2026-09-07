"""Custom vocabulary / glossary domain model (post-GA P0-3).

One `VocabularyEntry` per (organization, optional template) — organization-
wide by default (`template_id IS NULL`), optionally narrowed to a single
Template (e.g. different jargon for "Meeting" vs "Medical Consultation").
Resolved by `app.vocabulary.service.resolve_vocabulary`, using whichever
Template the conversation's existing config hierarchy
(`app.profiles.resolver.resolve_effective_config`) already decided
applies -- never a separate, parallel "which template" mechanism.

`terms` (hotwords) and `initial_prompt` are passed straight through to
`app.providers.speech_to_text.SpeechToTextProvider.transcribe()`, which
forwards them to faster-whisper's own `hotwords`/`initial_prompt`
parameters -- VocaDox never reinterprets or scores the vocabulary itself,
it only carries it to the ASR model as-is.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "template_id", name="uq_vocabulary_org_template"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL = applies organization-wide; set = applies only when this
    # Template is the conversation's effective template.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("templates.id", ondelete="CASCADE"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # A JSON array of individual terms (e.g. drug names, product names,
    # jargon) -- stored structured for admin editing, joined into a single
    # string at resolve time (see app.vocabulary.service).
    terms: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Free-form context sentence(s) -- faster-whisper's `initial_prompt`,
    # biases decoding style/spelling more broadly than individual hotwords.
    initial_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def as_snapshot(self) -> dict[str, Any]:
        """A plain-dict snapshot for `ProcessingRun.configuration_snapshot`
        -- provenance of which vocabulary (if any) actually applied to a
        given transcription run, spec §43's reproducibility requirement."""
        return {
            "vocabulary_entry_id": str(self.id),
            "name": self.name,
            "term_count": len(self.terms),
            "has_initial_prompt": self.initial_prompt is not None,
        }
