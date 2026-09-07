"""API request/response schemas for VocabularyEntry CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VocabularyCreateRequest(BaseModel):
    template_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    terms: list[str] = Field(default_factory=list, max_length=500)
    initial_prompt: str | None = Field(default=None, max_length=2000)


class VocabularyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    terms: list[str] | None = Field(default=None, max_length=500)
    initial_prompt: str | None = Field(default=None, max_length=2000)


class VocabularyResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    template_id: uuid.UUID | None
    name: str
    terms: list[str]
    initial_prompt: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
