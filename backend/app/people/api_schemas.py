"""API request/response schemas for KnownSpeaker CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnownSpeakerCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=500)


class KnownSpeakerUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=500)


class KnownSpeakerResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    display_name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
