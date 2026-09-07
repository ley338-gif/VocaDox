"""Pydantic request/response schemas for the DetectedSpeaker REST API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DetectedSpeakerResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    internal_label: str
    display_label: str | None
    participant_id: uuid.UUID | None
    assigned_by_user_id: uuid.UUID | None
    assigned_at: datetime | None
    has_voiceprint: bool
    suggested_known_speaker_id: uuid.UUID | None
    suggested_confidence: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SpeakerAssignmentRequest(BaseModel):
    participant_id: uuid.UUID | None = None
    display_label: str | None = Field(default=None, max_length=255)


class SpeakerEnrollRequest(BaseModel):
    known_speaker_id: uuid.UUID
