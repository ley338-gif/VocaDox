"""API request/response schemas for the Protokoll REST surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GenerateProtocolRequest(BaseModel):
    pass  # no parameters yet — generation always uses the conversation's current transcript


class ProtocolItemResponse(BaseModel):
    id: uuid.UUID
    protocol_section_id: uuid.UUID
    position: int
    item_type: str
    text: str
    responsible_label: str | None
    due_date: str | None
    completed: bool | None
    confidence: float | None
    manually_edited: bool

    model_config = {"from_attributes": True}


class ProtocolSectionResponse(BaseModel):
    id: uuid.UUID
    protocol_revision_id: uuid.UUID
    position: int
    section_type: str
    title: str
    summary: str
    start_ms: int | None
    end_ms: int | None
    confidence: float | None
    manually_edited: bool
    items: list[ProtocolItemResponse] = []

    model_config = {"from_attributes": True}


class ProtocolRevisionResponse(BaseModel):
    id: uuid.UUID
    protocol_id: uuid.UUID
    revision_number: int
    status: str
    created_at: datetime
    sections: list[ProtocolSectionResponse] = []

    model_config = {"from_attributes": True}


class ProtocolRevisionSummaryResponse(BaseModel):
    """The `.../revisions` list endpoint — summaries only, no section/item
    content, matching `app.documents.router`'s equivalent listing (the
    full revision browsing UI is a follow-up PR; this data ships now)."""

    id: uuid.UUID
    revision_number: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProtocolResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    current_revision_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    current_revision: ProtocolRevisionResponse | None = None

    model_config = {"from_attributes": True}


class ProtocolSourceResponse(BaseModel):
    """Mirrors the Fakten tab's evidence response shape (`{id,
    segment_start_ms, segment_text}`) plus a speaker label (a protocol
    source quote reads better attributed) and the real
    `transcript_segment_id`, needed for "Im Transkript öffnen" to target
    the exact segment (`TranscriptPanel`'s existing `focusSegmentId`
    scroll-and-highlight mechanism)."""

    id: uuid.UUID
    transcript_segment_id: uuid.UUID
    segment_start_ms: int
    segment_end_ms: int
    segment_text: str
    speaker_label: str | None
