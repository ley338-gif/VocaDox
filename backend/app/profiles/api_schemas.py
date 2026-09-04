"""API request/response schemas for the Model Profile / Processing Profile
admin surface (spec §18/§19). Global (platform-wide), not organization-
scoped — see app.templates.router's module docstring for why."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ModelProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    purpose: str
    provider: str
    model_identifier: str
    context_length: int
    temperature: float
    max_tokens: int
    structured_output: bool
    thinking_mode: str | None
    configuration: dict[str, Any] | None
    version: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelProfileCreateRequest(BaseModel):
    name: str
    purpose: str = "extraction"
    provider: str
    model_identifier: str
    context_length: int = 8192
    temperature: float = 0.0
    max_tokens: int = 2048
    structured_output: bool = True
    thinking_mode: str | None = None
    configuration: dict[str, Any] | None = None
    enabled: bool = True


class ModelProfileUpdateRequest(BaseModel):
    name: str | None = None
    provider: str | None = None
    model_identifier: str | None = None
    context_length: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    structured_output: bool | None = None
    thinking_mode: str | None = None
    configuration: dict[str, Any] | None = None
    enabled: bool | None = None


class ModelProfileVersionResponse(BaseModel):
    id: uuid.UUID
    model_profile_id: uuid.UUID
    version_number: int
    name: str
    provider: str
    model_identifier: str
    context_length: int
    temperature: float
    max_tokens: int
    structured_output: bool
    thinking_mode: str | None
    configuration: dict[str, Any] | None
    enabled: bool
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProcessingProfileResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_system_default: bool
    current_published_version_id: uuid.UUID | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProcessingProfileVersionResponse(BaseModel):
    id: uuid.UUID
    processing_profile_id: uuid.UUID
    version_number: int
    status: str
    speech_provider_config: dict[str, Any] | None
    diarization_provider_config: dict[str, Any] | None
    extraction_model_profile_id: uuid.UUID | None
    document_model_profile_id: uuid.UUID | None
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    prompt_id: uuid.UUID | None
    prompt_version_id: uuid.UUID | None
    language: str
    retention_policy_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None

    model_config = {"from_attributes": True}


class ProcessingProfileVersionCreateRequest(BaseModel):
    speech_provider_config: dict[str, Any] | None = None
    diarization_provider_config: dict[str, Any] | None = None
    extraction_model_profile_id: uuid.UUID | None = None
    document_model_profile_id: uuid.UUID | None = None
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    prompt_id: uuid.UUID | None = None
    prompt_version_id: uuid.UUID | None = None
    language: str = "auto"
    retention_policy_id: uuid.UUID | None = None


class ProcessingProfileCreateRequest(ProcessingProfileVersionCreateRequest):
    key: str
    name: str
    description: str | None = None
    is_system_default: bool = False
