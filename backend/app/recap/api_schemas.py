"""API request/response schemas for the Recap REST surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


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
