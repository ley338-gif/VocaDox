"""API request/response schemas for the Recap REST surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateRecapRequest(BaseModel):
    pass  # no parameters — generation always uses the conversation's current Document


class RecapRevisionResponse(BaseModel):
    id: uuid.UUID
    recap_id: uuid.UUID
    revision_number: int
    content: str
    language: str | None
    provider: str
    model_identifier: str
    status: str
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecapResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    current_revision_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    current_revision: RecapRevisionResponse | None = None

    model_config = {"from_attributes": True}


# -- Share links (post-GA P3-2) ------------------------------------------


class CreateShareLinkRequest(BaseModel):
    ttl_hours: int = Field(default=168, ge=1, le=720)  # default 7 days, max 30 days


class ShareLinkResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    token: str
    expires_at: datetime
    revoked_at: datetime | None
    created_by_user_id: uuid.UUID | None
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicRecapResponse(BaseModel):
    """Deliberately minimal -- only what an unauthenticated recipient
    needs to read the recap. Never the conversation title, participant
    names, or any other metadata beyond what the recap text itself
    already contains."""

    content: str
    revision_number: int
    approved_at: datetime | None
    expires_at: datetime
