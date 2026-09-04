"""API request/response schemas for the Template Engine / Prompt admin
surface. Global (platform-wide), not organization-scoped — see
app.templates.router's module docstring."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TemplateVersionResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    status: str
    extraction_categories: list[dict[str, Any]]
    presentation: list[dict[str, Any]]
    review_rules: dict[str, Any] | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None

    model_config = {"from_attributes": True}


class TemplateResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    current_published_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateCreateRequest(BaseModel):
    key: str
    name: str
    description: str | None = None
    extraction_categories: list[dict[str, Any]]
    presentation: list[dict[str, Any]]
    review_rules: dict[str, Any] | None = None


class TemplateVersionCreateRequest(BaseModel):
    extraction_categories: list[dict[str, Any]]
    presentation: list[dict[str, Any]]
    review_rules: dict[str, Any] | None = None


class PromptVersionResponse(BaseModel):
    id: uuid.UUID
    prompt_id: uuid.UUID
    version_number: int
    status: str
    system_prompt: str
    category_instructions: dict[str, str]
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None

    model_config = {"from_attributes": True}


class PromptResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    purpose: str
    current_published_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptCreateRequest(BaseModel):
    key: str
    name: str
    purpose: str = "extraction"
    system_prompt: str
    category_instructions: dict[str, str]


class PromptVersionCreateRequest(BaseModel):
    system_prompt: str
    category_instructions: dict[str, str]
