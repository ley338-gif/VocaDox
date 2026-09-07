"""Search index domain model (post-GA P0-1).

`SearchEntry` is a denormalized, one-row-per-searchable-unit index over
three source tables (`TranscriptSegment`, `ExtractedFact`,
`app.documents.models.Document`) — never a live join across them, so a
search query never needs to touch three different tables under
different authorization rules. `organization_id`/`group_id` are
denormalized from the owning `Conversation` at write time, mirroring
`app.longitudinal.models.FollowUpTask`'s own denormalization (see that
model's docstring): cross-conversation search/isolation checks never
need a join to be correct.

The actual full-text index (`tsv`, a generated `tsvector` column, GIN-
indexed) is deliberately NOT mapped here — see
`docs/architecture/adr/0030-search-index-dual-dialect.md` for why: the
test suite runs on SQLite (no `tsvector` type), production on Postgres.
The column/index exist in the real schema (created by raw DDL in the
migration) and are queried via `app.search.service`'s dialect-aware raw
SQL fragment; `content` (plain text, portable) is what every dialect
sees and can filter on directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class SearchSourceType(StrEnum):
    TRANSCRIPT_SEGMENT = "transcript_segment"
    EXTRACTED_FACT = "extracted_fact"
    DOCUMENT = "document"


class SearchEntry(Base):
    __tablename__ = "search_entries"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_search_entries_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # (source_type, source_id) identifies exactly one row in exactly one
    # of the three source tables -- never a shared/ambiguous id space.
    # A DOCUMENT entry's source_id is the Document id (not a specific
    # DocumentRevision id): re-composing always UPSERTs the same row
    # rather than accumulating one stale entry per past revision, the
    # same duplicate-avoidance reasoning as app.intelligence.service's
    # FactStatus.SUPERSEDED handling (PR #61).
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
