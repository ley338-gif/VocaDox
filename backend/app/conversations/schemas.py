"""Pydantic request/response schemas for the conversations + media REST API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.conversations.models import ConversationType, ParticipantType, PrivacyMode


class ConversationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    conversation_type: ConversationType = ConversationType.GENERAL
    organization_id: uuid.UUID
    external_reference: str | None = Field(default=None, max_length=255)
    external_reference_type: str | None = Field(default=None, max_length=64)
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD
    # Phase 6 (spec §19): the friendly Processing Profile name the user
    # picked when starting this conversation (e.g. "General", "Meeting").
    # Omitted/None means the SYSTEM DEFAULT layer applies (see
    # app.profiles.resolver) — unchanged pre-Phase-6 behavior.
    processing_profile_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    conversation_type: ConversationType | None = None
    external_reference: str | None = Field(default=None, max_length=255)
    external_reference_type: str | None = Field(default=None, max_length=64)
    privacy_mode: PrivacyMode | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    title: str
    description: str | None
    conversation_type: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    external_reference: str | None
    external_reference_type: str | None
    privacy_mode: str
    retention_policy_id: uuid.UUID | None
    processing_profile_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class MediaAssetResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    kind: str
    source_type: str
    original_filename: str | None
    content_type: str
    size_bytes: int
    sha256: str
    duration_ms: int | None
    sample_rate: int | None
    channels: int | None
    codec: str | None
    container: str | None
    derived_from_media_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    participant_type: ParticipantType = ParticipantType.UNKNOWN
    external_reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ParticipantUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    participant_type: ParticipantType | None = None
    external_reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ParticipantResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    display_name: str
    participant_type: str
    external_reference: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarkerCreateRequest(BaseModel):
    timestamp_ms: int = Field(ge=0)
    label: str | None = Field(default=None, max_length=255)
    note: str | None = None


class MarkerUpdateRequest(BaseModel):
    timestamp_ms: int | None = Field(default=None, ge=0)
    label: str | None = Field(default=None, max_length=255)
    note: str | None = None


class MarkerResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    timestamp_ms: int
    label: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    timestamp_ms: int | None = Field(default=None, ge=0)


class NoteUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    timestamp_ms: int | None = Field(default=None, ge=0)


class NoteResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    content: str
    timestamp_ms: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecordingFinalizeRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    original_filename: str | None = None
